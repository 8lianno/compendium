// Content script — injected into pages
// Currently minimal: the popup handles extraction via chrome.scripting.executeScript
// This file exists for future enhancements (e.g., selection-based clipping)

(() => {
  // Listen for messages from the popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "getHTML") {
      sendResponse({ html: document.documentElement.outerHTML, url: window.location.href });
    }
    return true;
  });
})();
