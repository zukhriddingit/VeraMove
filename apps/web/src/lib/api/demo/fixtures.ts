import type {
  JobView,
  ReportView,
  CallView,
} from "../types";

export const DEMO_JOB_ID = "demo-job-1";

export const demoJobSpec: JobView = {
  id: DEMO_JOB_ID,
  version: 1,
  status: "intake_complete",
  synthetic: true,
  homeType: "Apartment",
  bedrooms: 2,
  move: {
    originCity: "Rock Hill",
    originState: "SC",
    destinationCity: "Charlotte",
    destinationState: "NC",
    date: "2026-08-15",
    flexibilityDays: 1,
  },
  access: {
    originFloor: 2,
    originStairs: 20,
    originElevator: false,
    destinationFloor: 4,
    destinationStairs: 0,
    destinationElevator: true,
    longCarryFt: 80,
    destinationLongCarryFt: 25,
  },
  inventory: [
    { item: "Sofa", qty: 1 },
    { item: "Queen bed", qty: 1, notes: "Requires disassembly" },
  ],
  services: { packing: false, insuranceTier: "standard" },
  extras: {
    disassembly: true,
    storage: false,
    oversizedOrFragile: [],
  },
  notes: "",
  extractionSource: "voice",
  editedFields: [],
  fieldWarnings: {},
  missingFields: [],
  createdAt: "2026-07-18T14:12:00Z",
};

// Variant with missing required fields — blocks confirmation until user fills them.
export const demoJobSpecMissing: JobView = {
  ...demoJobSpec,
  access: { ...demoJobSpec.access, longCarryFt: 0 },
  services: { ...demoJobSpec.services, insuranceTier: "standard" },
  extractionSource: "document",
  missingFields: ["access.longCarryFt", "move.flexibilityDays"],
};

// Variant with parsing warnings — confirmable but flagged for review.
export const demoJobSpecWarnings: JobView = {
  ...demoJobSpec,
  extractionSource: "document",
  fieldWarnings: {
    "move.date": "Date read as '8/15' — assumed 2026. Please confirm.",
    "inventory": "OCR flagged 2 items with low confidence. Review quantities.",
  },
};


const REQ_LABELS = {
  ai_disclosure: "AI disclosure",
  friction_handled: "Friction handled",
  verified_leverage: "Verified leverage only",
  structured_ending: "Structured ending",
} as const;

export const demoCalls: CallView[] = [
  {
    id: "call-a",
    jobId: DEMO_JOB_ID,
    vendor: { id: "vendor-a", name: "ClearPath Movers", kind: "transparent" },
    status: "completed",
    outcome: "itemized_quote",
    headlineQuote: 1825,
    verifiedTotal: 1825,
    binding: true,
    fees: [
      { label: "Labor (3 movers, 6h)", amount: 1080 },
      { label: "Truck & mileage", amount: 385 },
      { label: "Stair carry (origin, 2nd floor)", amount: 120 },
      { label: "Long carry (80 ft)", amount: 90 },
      { label: "Standard valuation coverage", amount: 60 },
      { label: "Fuel surcharge", amount: 90 },
    ],
    hiddenFees: [],
    redFlags: [],
    requirements: [
      {
        id: "ai_disclosure",
        label: REQ_LABELS.ai_disclosure,
        state: "passed",
        evidence: {
          callId: "call-a",
          ts: "00:04",
          excerpt:
            "Agent: “Quick note — I'm an AI assistant calling on behalf of a customer. Is it OK to continue?”",
        },
      },
      {
        id: "friction_handled",
        label: REQ_LABELS.friction_handled,
        state: "passed",
        evidence: {
          callId: "call-a",
          ts: "02:18",
          excerpt:
            "Rep asked to text the quote. Agent asked for it read aloud item-by-item and confirmed each fee.",
        },
      },
      {
        id: "verified_leverage",
        label: REQ_LABELS.verified_leverage,
        state: "passed",
        evidence: {
          callId: "call-a",
          ts: "05:41",
          excerpt: "No competing quote referenced — this is the baseline call.",
        },
      },
      {
        id: "structured_ending",
        label: REQ_LABELS.structured_ending,
        state: "passed",
        evidence: {
          callId: "call-a",
          ts: "07:02",
          excerpt:
            "Agent read back binding total $1,825, availability Aug 15, and confirmed the hold reference.",
        },
      },
    ],
    transcript: [
      { ts: "00:04", speaker: "agent", text: "I'm an AI assistant calling on behalf of a customer moving from Rock Hill to Charlotte on August 15.", tag: "disclosure" },
      { ts: "02:18", speaker: "vendor", text: "Two-bed, second floor no elevator, 80-foot carry. That's a stair fee of $120 and a long-carry of $90." },
      { ts: "07:02", speaker: "agent", text: "So binding total $1,825, valid through Friday. Confirmed?", tag: "commitment" },
      { ts: "07:08", speaker: "vendor", text: "Confirmed. Hold reference CPM-4821." },
    ],
    recording: { url: "", durationSec: 428 },
    startedAt: "2026-07-18T14:18:00Z",
    endedAt: "2026-07-18T14:25:08Z",
  },
  {
    id: "call-b",
    jobId: DEMO_JOB_ID,
    vendor: { id: "vendor-b", name: "BudgetHaul Express", kind: "budget" },
    status: "completed",
    outcome: "itemized_quote",
    headlineQuote: 1150,
    verifiedTotal: 1850,
    binding: false,
    fees: [
      { label: "Headline base rate", amount: 1150 },
    ],
    hiddenFees: [
      { label: "Stair carry (revealed after questioning)", amount: 240, revealedAfterQuestioning: true },
      { label: "Long-carry surcharge", amount: 180, revealedAfterQuestioning: true },
      { label: "Fuel & mileage adjustment", amount: 210, revealedAfterQuestioning: true },
      { label: "Materials / shrink-wrap", amount: 70, revealedAfterQuestioning: true },
    ],
    redFlags: [
      {
        id: "rf-below-median",
        severity: "risk",
        message: "Headline quote is 36% below the comparison median.",
        evidence: {
          callId: "call-b",
          ts: "00:22",
          excerpt: "Rep quoted $1,150 flat before hearing floor, stairs, or carry details.",
        },
      },
      {
        id: "rf-nonbinding",
        severity: "caution",
        message: "Non-binding estimate — final price may change on move day.",
      },
    ],
    requirements: [
      { id: "ai_disclosure", label: REQ_LABELS.ai_disclosure, state: "passed", evidence: { callId: "call-b", ts: "00:03", excerpt: "Agent disclosed AI status before collecting any information." } },
      { id: "friction_handled", label: REQ_LABELS.friction_handled, state: "passed", evidence: { callId: "call-b", ts: "03:14", excerpt: "Agent pushed back three times to surface stair, long-carry, and fuel fees." } },
      { id: "verified_leverage", label: REQ_LABELS.verified_leverage, state: "pending", evidence: { callId: "call-b", ts: "—", excerpt: "No leverage was applied — this vendor was surveyed only." } },
      { id: "structured_ending", label: REQ_LABELS.structured_ending, state: "failed", evidence: { callId: "call-b", ts: "06:48", excerpt: "Rep declined to make the estimate binding; ended without a written hold." } },
    ],
    transcript: [
      { ts: "00:22", speaker: "vendor", text: "Two-bed local? I can do $1,150, easy." },
      { ts: "03:14", speaker: "agent", text: "Does that include stair carry from a second floor and an 80-foot parking carry?", tag: "hidden_fee" },
      { ts: "03:22", speaker: "vendor", text: "Oh — stairs are $240, long carry another $180, plus fuel adjustment around $210." },
      { ts: "06:48", speaker: "agent", text: "Can you make this binding at $1,850?", tag: "commitment" },
      { ts: "06:55", speaker: "vendor", text: "We only do non-binding estimates." },
    ],
    recording: { url: "", durationSec: 421 },
    startedAt: "2026-07-18T14:26:00Z",
    endedAt: "2026-07-18T14:33:01Z",
  },
  {
    id: "call-c",
    jobId: DEMO_JOB_ID,
    vendor: { id: "vendor-c", name: "PremierMove", kind: "premium" },
    status: "completed",
    outcome: "itemized_quote",
    headlineQuote: 2200,
    verifiedTotal: 1900,
    binding: true,
    fees: [
      { label: "Crew of 3 + 26' truck", amount: 1420 },
      { label: "Disassembly / reassembly", amount: 140 },
      { label: "Stair & long-carry", amount: 180 },
      { label: "Standard valuation coverage", amount: 60 },
      { label: "Packing materials (added in negotiation)", amount: 100 },
    ],
    hiddenFees: [],
    redFlags: [],
    requirements: [
      { id: "ai_disclosure", label: REQ_LABELS.ai_disclosure, state: "passed", evidence: { callId: "call-c", ts: "00:05", excerpt: "Disclosed AI caller and purpose before pricing discussion." } },
      { id: "friction_handled", label: REQ_LABELS.friction_handled, state: "passed", evidence: { callId: "call-c", ts: "04:02", excerpt: "Handled objection about matching ClearPath by re-anchoring on binding + inclusions." } },
      { id: "verified_leverage", label: REQ_LABELS.verified_leverage, state: "passed", evidence: { callId: "call-c", ts: "05:11", excerpt: "Agent cited ClearPath's verified binding quote of $1,825 (not a headline number)." } },
      { id: "structured_ending", label: REQ_LABELS.structured_ending, state: "passed", evidence: { callId: "call-c", ts: "08:20", excerpt: "Read back new binding total $1,900 including packing materials; hold ref PM-7710." } },
    ],
    transcript: [
      { ts: "00:05", speaker: "agent", text: "AI assistant calling on behalf of a customer, quoting a move Aug 15.", tag: "disclosure" },
      { ts: "02:40", speaker: "vendor", text: "Best I can do today is $2,200 binding, all-in." },
      { ts: "05:11", speaker: "agent", text: "I have a verified binding quote from ClearPath at $1,825 for the same scope. Can you match and include packing materials?", tag: "leverage" },
      { ts: "05:47", speaker: "vendor", text: "I can bring it to $1,900 binding and include the packing materials." },
      { ts: "08:20", speaker: "agent", text: "Confirming $1,900 binding, packing materials included, hold PM-7710.", tag: "commitment" },
    ],
    recording: { url: "", durationSec: 512 },
    negotiation: {
      beforeTotal: 2200,
      afterTotal: 1900,
      delta: -300,
      leverageVendorId: "vendor-a",
      addedInclusions: ["Packing materials"],
    },
    startedAt: "2026-07-18T14:34:00Z",
    endedAt: "2026-07-18T14:42:32Z",
  },
];

export const demoReport: ReportView = {
  jobId: DEMO_JOB_ID,
  synthetic: true,
  medianVerifiedTotal: 1850,
  cheapestVendorId: "vendor-a",
  ranking: [
    {
      vendorId: "vendor-c",
      vendorName: "PremierMove",
      score: 94,
      finalTotal: 1900,
      binding: true,
      label: "Best value",
      headlineTotal: 2200,
      verifiedTotal: 2200,
      negotiatedTotal: 1900,
      verificationState: "verified",
      availability: "Confirmed Aug 12",
      deposit: 200,
      concessions: ["Packing materials included", "Price honored through Aug 19"],
      hiddenFeeCount: 0,
      redFlagCount: 0,
      evidenceCount: 4,
      hasRecording: true,
      completeness: "complete",
      warnings: [],
      synthetic: true,
      reasons: [
        "Binding quote after negotiation",
        "Includes packing materials",
        "No hidden fees discovered",
        "$300 price improvement documented",
      ],
    },
    {
      vendorId: "vendor-a",
      vendorName: "ClearPath Movers",
      score: 90,
      finalTotal: 1825,
      binding: true,
      label: "Cheapest",
      headlineTotal: 1825,
      verifiedTotal: 1825,
      verificationState: "verified",
      availability: "Confirmed Aug 12",
      deposit: 150,
      concessions: [],
      hiddenFeeCount: 0,
      redFlagCount: 0,
      evidenceCount: 3,
      hasRecording: true,
      completeness: "complete",
      warnings: [],
      synthetic: true,
      reasons: [
        "Lowest binding total",
        "Fully itemized quote",
        "No red flags detected",
      ],
    },
    {
      vendorId: "vendor-b",
      vendorName: "BudgetHaul Express",
      score: 42,
      finalTotal: 1850,
      binding: false,
      label: "Highest risk",
      headlineTotal: 1180,
      verifiedTotal: 1850,
      verificationState: "partially_verified",
      availability: "Tentative — dispatch not confirmed",
      deposit: 400,
      concessions: [],
      hiddenFeeCount: 3,
      redFlagCount: 2,
      evidenceCount: 5,
      hasRecording: true,
      completeness: "partial",
      warnings: [
        "Headline price 36% below comparison median",
        "Stair, long-carry, and fuel fees revealed only after probing",
        "Estimate remained non-binding at call end",
      ],
      synthetic: true,
      reasons: [
        "Non-binding — final price may change on move day",
        "Multiple fees only revealed after questioning",
        "Headline price 36% below comparison median",
      ],
    },
  ],
  recommended: {
    vendorId: "vendor-c",
    label: "Best value",
    tradeoffs: [
      "$75 more than ClearPath's binding total, but includes packing materials (~$100 value).",
      "Highest score across binding-ness, completeness, and evidence.",
    ],
    savingsVsHighest: 300,
  },
  narrative: {
    whyThisVendor:
      "PremierMove closed as a binding quote at $1,900, added packing materials at no extra cost, and produced a written hold reference. Every material claim links to a timestamped transcript excerpt.",
    whyNotCheapest:
      "ClearPath is $75 cheaper on paper, but does not include packing materials. Adjusted for included services, PremierMove is the lower true cost with the same binding protection.",
    whatChanged:
      "PremierMove opened at $2,200. Using ClearPath's verified $1,825 binding quote as leverage, the rep committed to $1,900 binding with packing materials included — a $300 improvement — and issued hold reference PM-7710.",
    remainingUncertainty:
      "Elevator reservation at the destination building is customer-arranged. Long-carry distance was estimated from the floor plan; on-site walk on move day may adjust labor hours within the binding cap.",
    whatToVerify:
      "Before booking: confirm the written binding estimate references PM-7710 and lists packing materials, confirm the elevator reservation window, and confirm deposit refund policy in writing.",
  },
  warnings: [
    {
      id: "budget-headline",
      severity: "risk",
      message: "BudgetHaul's headline price is 36% below the comparison median — a common bait-and-switch signal.",
      vendorId: "vendor-b",
      ts: "02:14",
      excerpt: "Rep quoted $1,180 before any stair, long-carry, or fuel fees were disclosed.",
    },
    {
      id: "budget-nonbinding",
      severity: "risk",
      message: "BudgetHaul refused to make the estimate binding; the final price can change on move day.",
      vendorId: "vendor-b",
      ts: "06:48",
    },
    {
      id: "budget-hidden",
      severity: "caution",
      message: "Three hidden fees at BudgetHaul (stairs, long carry, fuel) were only revealed after direct questioning.",
      vendorId: "vendor-b",
      ts: "03:14",
    },
  ],
  evidenceIndex: [
    { callId: "call-a", vendorName: "ClearPath Movers", note: "Baseline itemized binding quote — 4/4 requirements passed.", ts: "08:20" },
    { callId: "call-b", vendorName: "BudgetHaul Express", note: "Hidden fees surfaced; non-binding — high risk.", ts: "06:48" },
    { callId: "call-c", vendorName: "PremierMove", note: "Negotiated $2,200 → $1,900 using ClearPath's verified quote as leverage.", ts: "08:20" },
  ],
  disclaimer: "Demo vendors and call evidence are synthetic or role-played.",
};
