import { useState, useRef, useCallback, useEffect } from "react";

// Web Speech API STT + TTS with graceful degradation.
export function useSpeech(lang) {
  const locale = lang === "tr" ? "tr-TR" : "en-US";
  const SR = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
  const ttsSupported = typeof window !== "undefined" && "speechSynthesis" in window;
  const sttSupported = !!SR;

  const [listening, setListening] = useState(false);
  const recRef = useRef(null);

  const startListening = useCallback((onResult) => {
    if (!SR) return;
    try {
      const rec = new SR();
      rec.lang = locale;
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onresult = (e) => {
        const text = e.results[0][0].transcript;
        onResult(text);
      };
      rec.onend = () => setListening(false);
      rec.onerror = () => setListening(false);
      recRef.current = rec;
      rec.start();
      setListening(true);
    } catch (e) {
      setListening(false);
    }
  }, [SR, locale]);

  const stopListening = useCallback(() => {
    try { recRef.current && recRef.current.stop(); } catch (e) {}
    setListening(false);
  }, []);

  const speak = useCallback((text) => {
    if (!ttsSupported || !text) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = locale;
      u.rate = 1;
      u.pitch = 1.05;
      window.speechSynthesis.speak(u);
    } catch (e) {}
  }, [ttsSupported, locale]);

  useEffect(() => () => { try { recRef.current && recRef.current.abort(); } catch (e) {} }, []);

  return { listening, startListening, stopListening, speak, sttSupported, ttsSupported };
}
