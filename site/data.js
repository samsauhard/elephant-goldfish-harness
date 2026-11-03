window.HARNESS_DATA = {
  "suites": {
    "development": {
      "description": "Six previously observed designs. The generic and original EGM baselines come from the earlier hard benchmark; grounded EGM is a later rerun. This is an exploratory historical comparison.",
      "original": {
        "unsupported": 10,
        "tokens": 53620,
        "minor": 5,
        "corrections": 2,
        "detected": 6,
        "expected": 6,
        "firstValid": 10,
        "invocations": 12,
        "attempts": 14,
        "completed": 6,
        "cases": 6,
        "major": 22,
        "controls": 3,
        "controlTotal": 3,
        "finalValid": 12
      },
      "grounded": {
        "unsupported": 7,
        "tokens": 83518,
        "minor": 25,
        "corrections": 4,
        "detected": 6,
        "expected": 6,
        "firstValid": 8,
        "invocations": 12,
        "attempts": 16,
        "completed": 6,
        "cases": 6,
        "major": 18,
        "controls": 2,
        "controlTotal": 3,
        "finalValid": 12
      },
      "direct": {
        "unsupported": null,
        "tokens": 19845,
        "minor": 5,
        "corrections": 2,
        "detected": 6,
        "expected": 6,
        "firstValid": 4,
        "finalValid": 6,
        "invocations": 6,
        "attempts": 8,
        "completed": 6,
        "cases": 6,
        "major": 9,
        "controls": 3,
        "controlTotal": 3
      }
    },
    "transfer": {
      "description": "Two new inventory designs, with two planted faults in the defective design. Original and grounded EGM ran in the same experiment. No generic or raw API baseline was run on this pair.",
      "original": {
        "unsupported": 5,
        "tokens": 26749,
        "minor": 1,
        "corrections": 2,
        "detected": 2,
        "expected": 2,
        "firstValid": 2,
        "invocations": 4,
        "attempts": 6,
        "completed": 2,
        "cases": 2,
        "major": 8,
        "controls": 1,
        "controlTotal": 1,
        "finalValid": 4
      },
      "grounded": {
        "unsupported": 1,
        "tokens": 38131,
        "minor": 8,
        "corrections": 3,
        "detected": 2,
        "expected": 2,
        "firstValid": 1,
        "invocations": 4,
        "attempts": 7,
        "completed": 2,
        "cases": 2,
        "major": 5,
        "controls": 1,
        "controlTotal": 1,
        "finalValid": 4
      },
      "direct": null
    }
  },
  "example": {
    "passageId": "26bb6020e8be-d6",
    "quote": "read available from stock for the requested SKU using an ordinary SELECT. If available is less than quantity, roll back and return 409. Otherwise issue UPDATE stock SET available=available-:quantity WHERE sku=:sku"
  },
  "recordedDate": "2026-11-02",
  "sourceCommit": "9d45a0516c31f3c64fda6ef9d36d4b20a2f5ae70"
};
