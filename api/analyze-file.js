import { analyzePayload } from "./rules.js";

function stripJsonText(text) {
  const trimmed = String(text || "").trim().replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim();
  const match = trimmed.match(/\{[\s\S]*\}/);
  return JSON.parse(match ? match[0] : trimmed);
}

function normalizeOpenAiAnalysis(parsed, fallback, payload) {
  const allowedRisks = new Set(["Low", "Medium", "High"]);
  const result = {
    ...fallback,
    provider: "OpenAI vision",
    providerMessage: "OpenAI analyzed the uploaded drawing bytes; PRUDENCE combined that reading with the selected rule packs.",
    documentName: parsed.documentName || payload.filename || fallback.documentName,
    jurisdiction: parsed.jurisdiction || payload.jurisdiction || fallback.jurisdiction,
    summary: parsed.summary || fallback.summary,
    extractedItems: Array.isArray(parsed.extractedItems) ? parsed.extractedItems : fallback.extractedItems,
    plan: parsed.plan && typeof parsed.plan === "object" ? { ...fallback.plan, ...parsed.plan } : fallback.plan,
    violations: Array.isArray(parsed.violations) && parsed.violations.length ? parsed.violations : fallback.violations,
  };
  const score = Number(parsed.score);
  const coverage = Number(parsed.coverage);
  if (Number.isFinite(score)) result.score = Math.max(0, Math.min(100, Math.round(score)));
  if (Number.isFinite(coverage)) result.coverage = Math.max(0, Math.min(100, Math.round(coverage)));
  if (allowedRisks.has(parsed.risk)) result.risk = parsed.risk;
  if (parsed.status) result.status = parsed.status;
  return result;
}

async function openAiDocumentAnalysis(payload, fallback) {
  if (fallback.provider === "Vercel trained rule engine") return fallback;
  const apiKey = process.env.OPENAI_API_KEY || process.env.PRUDENCE_OPENAI_API_KEY;
  if (!apiKey) return fallback;

  const encodedData = String(payload.data || payload.base64 || "").replace(/^data:[^,]+,/, "").replace(/\s/g, "");
  const mimeType = String(payload.mimeType || payload.type || "application/octet-stream");
  if (!encodedData || !mimeType.toLowerCase().startsWith("image/") || encodedData.length > 18_000_000) {
    return {
      ...fallback,
      providerMessage: "OpenAI is configured; this uploaded file type is using the deterministic local rule engine for stable demo results.",
    };
  }

  const prompt = [
    "You are PRUDENCE, an Indian construction compliance agent.",
    "Analyze the uploaded construction plan image visually and return strict JSON only.",
    "Use this exact schema:",
    "{\"documentName\": string, \"jurisdiction\": string, \"score\": number, \"coverage\": number, \"risk\": \"Low|Medium|High\", \"status\": string, \"summary\": string, \"extractedItems\": string[], \"plan\": {\"sheetType\": string, \"scale\": string, \"plotCoverage\": string, \"farFsi\": string, \"setbackBand\": string, \"parking\": string}, \"violations\": [{\"severity\": \"CRITICAL|MAJOR|MINOR\", \"title\": string, \"required\": string, \"found\": string, \"delta\": string, \"note\": string, \"clause\": string, \"evidence\": string, \"calculation\": string}]}",
    "If a dimension or value is not legible, say 'Not legible' instead of inventing it.",
    "Focus on setbacks, FAR/FSI, coverage, parking count, road width, fire access, stairs, corridors, refuge areas, and RERA disclosure gaps.",
    `File metadata: ${JSON.stringify({ filename: payload.filename, size: payload.size, mimeType, jurisdiction: payload.jurisdiction })}`,
  ].join(" ");

  const body = {
    model: process.env.PRUDENCE_OPENAI_MODEL || process.env.OPENAI_MODEL || "gpt-4o-mini",
    messages: [{
      role: "user",
      content: [
        { type: "text", text: prompt },
        { type: "image_url", image_url: { url: `data:${mimeType};base64,${encodedData}` } },
      ],
    }],
    temperature: 0.1,
    max_tokens: 1400,
    response_format: { type: "json_object" },
  };

  try {
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      return {
        ...fallback,
        providerMessage: `OpenAI returned HTTP ${response.status}; using deterministic PRUDENCE rule checks.`,
      };
    }
    const data = await response.json();
    const content = data?.choices?.[0]?.message?.content || "";
    return normalizeOpenAiAnalysis(stripJsonText(content), fallback, payload);
  } catch (error) {
    return {
      ...fallback,
      providerMessage: "OpenAI analysis was unavailable; using deterministic PRUDENCE rule checks.",
    };
  }
}

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

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  try {
    const payload = parseBody(req);
    const result = await openAiDocumentAnalysis(payload, analyzePayload(payload));
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
