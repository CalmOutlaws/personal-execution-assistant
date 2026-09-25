/* Quick Add voice input (Web Speech API, text only).
 * AI disclosure (CS50): created with AI assistance, reviewed by author.
 * AI disclosure (debug fix): onerror/onend/lang handling updated with AI
 * assistance; typed flow, parser.py, and persistence unchanged.
 * Flow: SpeechRecognition -> #text field -> POST /quick-add. No auto-submit,
 * no network calls, no external service; parser.py + confirmation unchanged. */
(function () {
  "use strict";
  var BUTTON_ID = "voice-input-button";
  var INPUT_ID = "text";
  var STATUS_ID = "voice-input-status";
  var PRIMARY_LANG = "en-IN";
  var FALLBACK_LANG = "en-US";
  var LABELS = {
    idle: "Start voice input",
    listening: "Listening...",
    success: "Voice captured",
    error: "Try again",
    unsupported: "Voice input unavailable"
  };
  function getConstructor() {
    if (typeof window === "undefined") return null;
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }
  function isSupported() { return Boolean(getConstructor()); }
  function setState(button, status, state, detail) {
    var label = detail || LABELS[state] || LABELS.idle;
    if (button) {
      button.disabled = (state === "unsupported" || state === "listening");
      button.setAttribute("aria-pressed", state === "listening" ? "true" : "false");
      button.setAttribute("data-voice-state", state);
      var span = button.querySelector("[data-voice-label]");
      if (span) span.textContent = label;
      else button.textContent = label;
      if (state === "unsupported") button.setAttribute("aria-disabled", "true");
    }
    if (status) {
      status.textContent = label;
      status.setAttribute("data-voice-state", state);
    }
  }
  function friendlyError(name) {
    if (name === "not-allowed") {
      return "Microphone permission was denied (not-allowed).";
    }
    if (name === "service-not-allowed") {
      return "Microphone blocked by the browser or page context (service-not-allowed).";
    }
    if (name === "no-speech") {
      return "No speech was detected (no-speech). Try again.";
    }
    if (name === "audio-capture") {
      return "No microphone was available (audio-capture). Try again.";
    }
    if (name === "network") {
      return "Speech recognition is unavailable in this browser right now (network). Try another browser or type your input.";
    }
    if (name === "aborted") {
      return "Voice input was stopped (aborted). Try again.";
    }
    if (name === "language-not-supported" || name === "bad-grammar") {
      return "Voice language is unsupported (" + name + "). Retrying in English.";
    }
    if (name) {
      return "Voice input failed (" + name + "). Try again.";
    }
    return "Voice input failed. Try again.";
  }
  function writeTranscript(input, transcript) {
    var cleaned = (transcript || "").trim();
    if (!cleaned) return false;
    input.value = cleaned;
    input.focus();
    return true;
  }
  function handleResult(input, button, status, event) {
    var transcript = "";
    try {
      if (event && event.results && event.results.length > 0) {
        transcript = event.results[0][0].transcript || "";
      }
    } catch (err) { transcript = ""; }
    if (writeTranscript(input, transcript)) {
      status.__voiceError = "";
      setState(button, status, "success");
    }
    else setState(button, status, "error", "No speech was detected (empty result). Try again.");
  }
  function handleError(recognition, button, status, name) {
    var detail = friendlyError(name);
    status.__voiceError = detail;
    setState(button, status, "error", detail + " Typed input still works.");
    /* Common Chrome case: "language-not-supported" for en-IN. Retry once in
     * widely supported en-US instead of leaving the user stuck. */
    if ((name === "language-not-supported" || name === "bad-grammar") &&
        recognition && !recognition.__triedFallbackLang) {
      recognition.__triedFallbackLang = true;
      try { recognition.lang = FALLBACK_LANG; } catch (err) {}
    }
    /* Chrome network-backed recognition can also reject en-IN with a bare
     * "network" error. Retry once in en-US before surfacing failure. */
    if (name === "network" && recognition && !recognition.__triedFallbackLang) {
      recognition.__triedFallbackLang = true;
      try { recognition.lang = FALLBACK_LANG; } catch (err) {}
      status.__voiceError = detail + " Retried voice language in English (en-US).";
      setState(button, status, "error", status.__voiceError + " Typed input still works.");
    }
  }
  function startRecognition(recognition, button, status) {
    if (recognition.__listening) {
      try { recognition.stop(); } catch (err) {}
      return;
    }
    status.__voiceError = "";
    setState(button, status, "listening");
    try { recognition.start(); }
    catch (err) {
      var detail = friendlyError("");
      status.__voiceError = detail;
      setState(button, status, "error", detail + " Typed input still works.");
    }
  }
  function init() {
    var button = document.getElementById(BUTTON_ID);
    var input = document.getElementById(INPUT_ID);
    var status = document.getElementById(STATUS_ID);
    if (!button || !input) return;
    var Recognition = getConstructor();
    if (!Recognition) {
      setState(button, status, "unsupported");
      if (status) status.textContent = "Voice input is not supported in this browser.";
      return;
    }
    var recognition = new Recognition();
    recognition.lang = PRIMARY_LANG;
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.__listening = false;
    recognition.__triedFallbackLang = false;
    recognition.__sawResult = false;
    recognition.onresult = function (event) {
      recognition.__sawResult = true;
      handleResult(input, button, status, event);
    };
    recognition.onerror = function (event) {
      var name = event && event.error ? event.error : "";
      handleError(recognition, button, status, name);
    };
    recognition.onstart = function () {
      recognition.__listening = true;
      recognition.__sawResult = false;
      status.__voiceError = "";
    };
    recognition.onend = function () {
      recognition.__listening = false;
      var current = button.getAttribute("data-voice-state");
      /* Never overwrite a specific error/success result with generic idle:
       * onerror fires before onend, and success lands before onend too. */
      if (current === "error" || current === "success") {
        if (current === "error" && status.__voiceError) {
          setState(button, status, "error", status.__voiceError + " Typed input still works.");
        } else {
          button.disabled = false;
        }
        return;
      }
      if (current === "listening") setState(button, status, "idle");
      else if (current !== "unsupported") button.disabled = false;
    };
    button.addEventListener("click", function () {
      startRecognition(recognition, button, status);
    });
    setState(button, status, "idle");
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  window.__quickAddVoice = {
    isSupported: isSupported,
    getSpeechRecognitionConstructor: getConstructor,
    writeTranscriptToInput: writeTranscript,
    friendlyErrorMessage: friendlyError,
    setState: setState
  };
})();

