module.exports = async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const {
    GITHUB_TOKEN,
    GITHUB_OWNER,
    GITHUB_REPO,
    GITHUB_WORKFLOW_ID = "latest_topic_pipeline.yml",
    GITHUB_REF = "main",
    VIDEO_REQUEST_ACCESS_CODE = "",
  } = process.env;

  if (!GITHUB_TOKEN || !GITHUB_OWNER || !GITHUB_REPO) {
    return res.status(500).json({ error: "Server is missing GitHub configuration." });
  }

  const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {});
  const topic = String(body.topic || "").trim();
  const sourceText = String(body.sourceText || "").trim();
  const notes = String(body.notes || "").trim();
  const channel = String(body.channel || "navadisha").trim().toLowerCase();
  const privacy = String(body.privacy || "public").trim().toLowerCase();
  const language = String(body.language || "en").trim();
  const dryRun = String(body.dryRun || "false").trim().toLowerCase();
  const accessCode = String(body.accessCode || "").trim();

  if (!topic) {
    return res.status(400).json({ error: "Topic is required." });
  }
  if (!sourceText) {
    return res.status(400).json({ error: "Source text is required." });
  }
  if (!["private", "unlisted", "public"].includes(privacy)) {
    return res.status(400).json({ error: "Invalid privacy value." });
  }
  if (!["navadisha", "childishdreamer"].includes(channel)) {
    return res.status(400).json({ error: "Invalid channel value." });
  }
  if (!["en", "te", "hi", "en-GB", "en-AU"].includes(language)) {
    return res.status(400).json({ error: "Invalid language value." });
  }
  if (VIDEO_REQUEST_ACCESS_CODE && accessCode !== VIDEO_REQUEST_ACCESS_CODE) {
    return res.status(403).json({ error: "Invalid access code." });
  }

  const dispatchResponse = await fetch(
    `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW_ID}/dispatches`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${GITHUB_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "youtube-auto-vercel",
      },
      body: JSON.stringify({
        ref: GITHUB_REF,
        inputs: {
          channel,
          source_topic: topic,
          source_text: sourceText,
          source_notes: notes,
          privacy,
          language,
          dry_run: dryRun === "true" ? "true" : "false",
        },
      }),
    }
  );

  if (!dispatchResponse.ok) {
    const errorText = await dispatchResponse.text();
    return res.status(500).json({
      error: "Failed to trigger GitHub workflow.",
      details: errorText,
    });
  }

  return res.status(200).json({
    ok: true,
    message: "Video request submitted.",
    actionsUrl: `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW_ID}`,
  });
};
