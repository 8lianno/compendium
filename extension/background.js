// Background service worker for Compendium Web Clipper
// Handles extension lifecycle events

chrome.runtime.onInstalled.addListener(() => {
  console.log("Compendium Web Clipper installed");
});
