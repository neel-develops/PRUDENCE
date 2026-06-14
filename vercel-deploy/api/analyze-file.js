import { analyzePayload } from "./rules.js";

function parseBody(req) {
  if (!req.body) return {};
  if (typeof req.body === "string") {
    try {
      return JSON.parse(req.body);
    } catch {
      return {};
    }
  }
  return req.body;
}

export default function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  try {
    const payload = parseBody(req);
    const result = analyzePayload(payload);
    res.status(200).json(result);
  } catch (error) {
    res.status(200).json({
      provider: "Vercel fallback",
      providerMessage: error instanceof Error ? error.message : "Unknown analysis error",
      documentName: "uploaded-drawing",
      score: 35,
      coverage: 0,
      risk: "High",
      status: "Review Required",
      summary: "The deployed analysis route caught an error and returned a safe fallback.",
      extractedItems: ["Upload was received, but the rule engine could not complete."],
      plan: {},
      rulePacks: [],
      ruleResults: [],
      ruleSummary: { checked: 0, pass: 0, fail: 0, missing: 0, review: 0, textCharacters: 0 },
      annotations: [],
      violations: [{
        severity: "MAJOR",
        title: "Analysis Error",
        note: "Try uploading the drawing again or use the trained Green Heights demo image.",
      }],
    });
  }
}
