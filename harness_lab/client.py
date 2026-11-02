"""Small local OpenAI-compatible HTTP client with explicit request accounting."""
import ipaddress
import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib import error, parse, request


class BudgetExceeded(RuntimeError):
    pass


class ModelError(RuntimeError):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_base_url(value):
    parsed = parse.urlsplit(value)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Local API base must be an http loopback URL without credentials/query")
    try:
        loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        loopback = parsed.hostname == "localhost"
    if not loopback or parsed.path.rstrip("/") != "/v1":
        raise ValueError("Use a loopback OpenAI-compatible base URL ending in /v1")
    # Reject invalid ports early.
    _ = parsed.port
    return value.rstrip("/")


def load_key(config):
    """Read an explicitly configured credential source; never search or log keys."""
    env_name = config.get("api_key_env", "HARNESS_API_KEY")
    value = os.environ.get(env_name, "")
    if value:
        return value
    database = config.get("api_key_sqlite_path")
    if database:
        # Existing FreeLLM router setting, opened read-only. The key is not copied.
        uri = Path(database).expanduser().resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = 'unified_api_key'"
            ).fetchone()
        if not row or not isinstance(row[0], str) or not row[0].strip():
            raise ValueError("Existing FreeLLM database has no unified API key")
        return row[0].strip()
    key_file = config.get("api_key_file")
    if key_file:
        path = Path(key_file).expanduser()
        if path.stat().st_size > 65536:
            raise ValueError("Credential source exceeds 64 KiB")
        text = path.read_text(encoding="utf-8-sig")
        field = config.get("api_key_field")
        if field:
            value = json.loads(text)
            for part in field.split("."):
                value = value[part]
        else:
            value = text.strip()
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Configured credential source does not contain a string key")
        return value.strip()
    return ""


class LocalClient:
    mode = "live"

    def __init__(self, config, run_dir=None, last_dispatch=None):
        self.base_url = local_base_url(config["base_url"])
        self.model = config["model"]
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("A model ID is required")
        self.max_requests = config.get("max_requests", 12)
        self.max_output_tokens = config.get("max_output_tokens", 2500)
        self.timeout = config.get("timeout_seconds", 60)
        self.retries = config.get("transport_retries", 1)
        self.min_interval = config.get("min_interval_seconds", 0)
        for label, value, minimum, maximum in (
            ("max_requests", self.max_requests, 1, 100),
            ("max_output_tokens", self.max_output_tokens, 64, 16384),
            ("timeout_seconds", self.timeout, 1, 300),
            ("transport_retries", self.retries, 0, 3),
            ("min_interval_seconds", self.min_interval, 0, 60),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError("Invalid " + label)
        self.json_mode = config.get("json_mode", True)
        if type(self.json_mode) is not bool:
            raise ValueError("json_mode must be boolean")
        self._key = load_key(config)
        self._opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
        self.run_dir = Path(run_dir) if run_dir else None
        self.attempts = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.usage_available = False
        self.resolved_models = set()
        self._last_attempt = last_dispatch

    @property
    def last_dispatch(self):
        """Monotonic dispatch time, reusable across sequential evaluation clients."""
        return self._last_attempt

    def _redact(self, text):
        return text.replace(self._key, "[REDACTED]") if self._key else text

    def _log(self, record):
        if self.run_dir:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            with (self.run_dir / "trace.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(self._redact(json.dumps(record, ensure_ascii=False)) + "\n")

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = "Bearer " + self._key
        return headers

    def models(self):
        req = request.Request(self.base_url + "/models", headers=self._headers())
        try:
            with self._opener.open(req, timeout=min(self.timeout, 10)) as response:
                data = json.loads(response.read(2_000_001))
        except error.HTTPError as exc:
            raise ModelError("Model discovery returned HTTP %s" % exc.code) from None
        except (error.URLError, TimeoutError, OSError, ValueError):
            raise ModelError("Model discovery failed; check local service, tunnel, and credentials") from None
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise ModelError("Endpoint did not return an OpenAI-compatible model list")
        return [item["id"] for item in data["data"]
                if isinstance(item, dict) and isinstance(item.get("id"), str)]

    def complete(self, messages, *, role):
        body = {"model": self.model, "messages": messages, "temperature": 0.2,
                "max_tokens": self.max_output_tokens, "stream": False}
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        encoded = json.dumps(body).encode("utf-8")
        if len(encoded) > 200_000:
            raise ModelError("Model request exceeds the 200 KB context payload limit")
        for retry in range(self.retries + 1):
            if self.attempts >= self.max_requests:
                self._log({"event": "budget_exhausted", "role": role, "attempts": self.attempts})
                raise BudgetExceeded("HTTP request budget exhausted")
            if self._last_attempt is not None:
                delay = self.min_interval - (time.monotonic() - self._last_attempt)
                if delay > 0:
                    self._log({"event": "pacing", "role": role, "wait_seconds": round(delay, 2)})
                    time.sleep(delay)
            self.attempts += 1
            attempt = self.attempts
            self._log({"event": "request", "attempt": attempt, "role": role, "model": self.model,
                       "messages": messages, "max_tokens": self.max_output_tokens})
            started = time.monotonic()
            self._last_attempt = started
            status = None
            transient = False
            retry_after = None
            try:
                req = request.Request(self.base_url + "/chat/completions", data=encoded,
                                      headers=self._headers(), method="POST")
                with self._opener.open(req, timeout=self.timeout) as response:
                    raw = response.read(2_000_001)
                    routed_via = response.headers.get("X-Routed-Via")
                if len(raw) > 2_000_000:
                    raise ModelError("Model HTTP response exceeds 2 MB")
                data = json.loads(raw)
                # Even rejected/truncated generations may consume tokens.
                usage = (data.get("usage") or {}) if isinstance(data, dict) else {}
                if not isinstance(usage, dict):
                    usage = {}
                for key in self.usage:
                    value = usage.get(key)
                    if type(value) is int and value >= 0:
                        self.usage[key] += value
                        self.usage_available = True
                choice = data["choices"][0]
                text = choice["message"]["content"]
                if choice.get("finish_reason") == "length":
                    raise ModelError("Model output was truncated; increase max_output_tokens")
                if not isinstance(text, str) or not text.strip():
                    raise ModelError("Model returned no text")
                duration = round((time.monotonic() - started) * 1000, 2)
                resolved_model = data.get("model", self.model)
                if isinstance(resolved_model, str):
                    self.resolved_models.add(resolved_model)
                text = self._redact(text)
                self._log({"event": "response", "attempt": attempt, "role": role,
                           "text": text, "usage": usage, "latency_ms": duration,
                           "resolved_model": resolved_model, "routed_via": routed_via})
                return {"text": text, "usage": usage, "latency_ms": duration}
            except error.HTTPError as exc:
                status = exc.code
                transient = status in (408, 429, 500, 502, 503, 504)
                message = "Model API returned HTTP %s" % status
                value = exc.headers.get("Retry-After") if exc.headers else None
                if value:
                    try:
                        retry_after = max(0.0, float(value))
                    except ValueError:
                        try:
                            until = parsedate_to_datetime(value)
                            retry_after = max(0.0, (until - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError, OverflowError):
                            pass
                if retry_after is not None and retry_after > 60:
                    # Do not retry before a longer server-requested cooldown.
                    transient = False
                    message += "; server requests a cooldown longer than 60 seconds; retry later"
            except (error.URLError, TimeoutError, OSError):
                transient = True
                message = "Local model connection failed or timed out"
            except (ValueError, KeyError, IndexError, TypeError):
                message = "Model API response is not valid chat-completion JSON"
            except ModelError as exc:
                message = str(exc)
            self._log({"event": "error", "attempt": attempt, "role": role, "status": status,
                       "error": message, "retry_after_seconds": retry_after,
                       "latency_ms": round((time.monotonic()-started)*1000, 2)})
            if not transient or retry >= self.retries:
                raise ModelError(message) from None
            delay = retry_after if retry_after is not None else (2 if status == 429 else min(0.25 * (2 ** retry), 2))
            self._log({"event": "retry_wait", "role": role, "wait_seconds": delay})
            time.sleep(delay)
        raise ModelError("Model request failed")


class ScriptedClient:
    """Canned responses for an honest, reproducible plumbing demo; no model calls."""
    mode = "scripted"
    model = "offline-fixtures-not-a-model"

    def __init__(self, responses, run_dir=None):
        self.responses = list(responses)
        self.run_dir = Path(run_dir) if run_dir else None
        self.attempts = 0
        self.usage = {}
        self.usage_available = False

    def complete(self, messages, *, role):
        if self.attempts >= len(self.responses):
            raise BudgetExceeded("Scripted response sequence exhausted")
        text = json.dumps(self.responses[self.attempts], ensure_ascii=False)
        self.attempts += 1
        if self.run_dir:
            with (self.run_dir / "trace.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"event": "scripted_call", "attempt": self.attempts,
                                         "role": role, "messages": messages, "text": text}) + "\n")
        return {"text": text, "usage": {}, "latency_ms": 0.0}
