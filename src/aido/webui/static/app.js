// Minimal helpers. Real interaction lives in templates' inline scripts.
globalThis.aido = {
  postJSON: async function (url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const text = await r.text();
      throw new Error(`POST ${url} failed: ${r.status} ${text}`);
    }
    return r.json();
  },
};
