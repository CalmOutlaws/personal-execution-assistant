/* EXECUTE browser notifications V1 (client-side only).
 * AI disclosure (CS50): created with AI assistance, reviewed by author.
 * Permission only after explicit click. Polls dashboard every 60 seconds,
 * dedupes via localStorage. Works only while app is open in the browser.
 */
(function () {
  "use strict";
  var BUTTON_ID = "enable-notifications-button";
  var STATUS_ID = "notification-status";
  var STORAGE_KEY = "execute.notificationPreference";
  var NOTIFIED_KEY = "execute.notifiedItems";
  var POLL_MS = 60 * 1000;
  var DUE_SOON_MS = 15 * 60 * 1000;
  function supported() {
    return typeof window !== "undefined" && ("Notification" in window);
  }
  function preference() {
    try { return window.localStorage.getItem(STORAGE_KEY); }
    catch (err) { return null; }
  }
  function setPreference(value) {
    try { window.localStorage.setItem(STORAGE_KEY, value); }
    catch (err) {}
  }
  function readNotified() {
    try { return JSON.parse(window.localStorage.getItem(NOTIFIED_KEY) || "{}"); }
    catch (err) { return {}; }
  }
  function writeNotified(value) {
    try { window.localStorage.setItem(NOTIFIED_KEY, JSON.stringify(value)); }
    catch (err) {}
  }
  function setStatus(text) {
    var el = document.getElementById(STATUS_ID);
    if (el) el.textContent = text;
  }
  function refreshStatus() {
    var button = document.getElementById(BUTTON_ID);
    if (!supported()) {
      setStatus("Browser notifications are not supported in this browser.");
      if (button) button.disabled = true;
      return;
    }
    var state = (typeof Notification !== "undefined" && Notification.permission) || "default";
    if (state === "granted") {
      setStatus("Notifications enabled on this device while EXECUTE is open.");
      if (button) button.disabled = true;
    } else if (state === "denied") {
      setStatus("Notifications are blocked. Allow them in browser settings.");
      if (button) button.disabled = true;
    } else {
      setStatus("Notifications are off.");
      if (button) button.disabled = false;
    }
  }
  function markNotified(key) {
    var seen = readNotified();
    seen[key] = Date.now();
    var cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
    Object.keys(seen).forEach(function (k) {
      if (seen[k] < cutoff) delete seen[k];
    });
    writeNotified(seen);
  }
  function alreadyNotified(key, ttlMs) {
    var seen = readNotified();
    if (!seen[key]) return false;
    return (Date.now() - seen[key]) < ttlMs;
  }
  function parseTimestamp(value) {
    if (!value) return null;
    var parsed = new Date(String(value).replace(" ", "T"));
    return isNaN(parsed.getTime()) ? null : parsed;
  }
  function collectCandidates() {
    var nodes = document.querySelectorAll(".notify-item[data-when]");
    var out = [];
    nodes.forEach(function (node) {
      out.push({
        key: node.getAttribute("data-notify-key") || node.textContent.trim().slice(0, 80),
        title: node.getAttribute("data-notify-title") || "EXECUTE reminder",
        when: parseTimestamp(node.getAttribute("data-when")),
        kind: node.getAttribute("data-notify-kind") || "item"
      });
    });
    return out;
  }
  function notifyItem(title, body, key) {
    try {
      new Notification(title, { body: body });
      markNotified(key);
    } catch (err) {}
  }
  function checkDue() {
    if (!supported()) return;
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    var now = Date.now();
    collectCandidates().forEach(function (item) {
      if (!item.when) {
        if (item.kind === "overdue" && !alreadyNotified(item.key, 24 * 60 * 60 * 1000)) {
          notifyItem(item.title, "This item is overdue.", item.key);
        }
        return;
      }
      var diff = item.when.getTime() - now;
      if (diff <= DUE_SOON_MS && diff >= -24 * 60 * 60 * 1000) {
        if (!alreadyNotified(item.key, 12 * 60 * 60 * 1000)) {
          notifyItem(item.title, diff < 0 ? "This item is overdue." : "Due soon.", item.key);
        }
      }
    });
  }
  function requestPermission() {
    if (!supported()) { refreshStatus(); return; }
    setPreference("enabled");
    try {
      var result = Notification.requestPermission();
      if (result && typeof result.then === "function") {
        result.then(function () { refreshStatus(); checkDue(); });
      } else { refreshStatus(); }
    } catch (err) { refreshStatus(); }
  }
  function init() {
    var button = document.getElementById(BUTTON_ID);
    if (button) button.addEventListener("click", requestPermission);
    refreshStatus();
    if (supported()) {
      window.setInterval(checkDue, POLL_MS);
      checkDue();
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
  window.__executeNotifications = {
    isSupported: supported,
    checkDue: checkDue,
    refreshStatus: refreshStatus,
    alreadyNotified: alreadyNotified,
    markNotified: markNotified
  };
})();

