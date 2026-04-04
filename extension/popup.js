const statusEl = document.getElementById("status");
const clipBtn = document.getElementById("clipBtn");
const infoEl = document.getElementById("info");

const WS_URL = "ws://127.0.0.1:17394/ws/clip";

clipBtn.addEventListener("click", async () => {
  statusEl.className = "status loading";
  statusEl.textContent = "Clipping...";
  clipBtn.disabled = true;

  try {
    // Get the current tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("No active tab");

    // Execute content script to get page HTML
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => document.documentElement.outerHTML,
    });

    const html = results[0]?.result;
    if (!html) throw new Error("Could not read page content");

    // Send to Compendium via WebSocket
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      ws.send(JSON.stringify({ url: tab.url, html }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.status === "success") {
        statusEl.className = "status success";
        statusEl.textContent = data.message;
        infoEl.textContent = "Saved to raw/";
      } else if (data.status === "duplicate") {
        statusEl.className = "status idle";
        statusEl.textContent = "Already clipped";
      } else {
        statusEl.className = "status error";
        statusEl.textContent = data.message || "Clip failed";
      }
      ws.close();
      clipBtn.disabled = false;
    };

    ws.onerror = () => {
      statusEl.className = "status error";
      statusEl.textContent = "Cannot connect to Compendium";
      infoEl.textContent = "Is the desktop app running?";
      clipBtn.disabled = false;
    };

    // Timeout after 10 seconds
    setTimeout(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
        statusEl.className = "status error";
        statusEl.textContent = "Clip timed out";
        clipBtn.disabled = false;
      }
    }, 10000);
  } catch (err) {
    statusEl.className = "status error";
    statusEl.textContent = err.message;
    clipBtn.disabled = false;
  }
});
