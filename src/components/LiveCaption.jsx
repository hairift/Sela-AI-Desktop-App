/* eslint-disable react/prop-types */
import { useState, useEffect, useRef } from "react";
import QRCode from "qrcode";

const URL_PATTERN = /(https?:\/\/[^\s]+)/g;
const TRAILING_PUNCTUATION = /[.,!?;:)\]]$/;
const QR_VISIBLE_MS = 20000;

function getCleanUrl(rawUrl) {
  let url = rawUrl;

  while (TRAILING_PUNCTUATION.test(url)) {
    url = url.slice(0, -1);
  }

  return url;
}

function extractLinks(text = "") {
  return Array.from(text.matchAll(URL_PATTERN))
    .map((match) => getCleanUrl(match[0]))
    .filter(Boolean);
}

function removeLinks(text = "") {
  return text
    .replace(URL_PATTERN, "")
    .replace(/\s+/g, " ")
    .trim();
}

function TimedQrCard({ url }) {
  const [qrSrc, setQrSrc] = useState("");
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    let active = true;

    QRCode.toDataURL(url, {
      width: 160,
      margin: 1,
      color: {
        dark: "#111827",
        light: "#ffffff",
      },
    }).then((src) => {
      if (active) setQrSrc(src);
    }).catch(() => {
      if (active) setQrSrc("");
    });

    return () => {
      active = false;
    };
  }, [url]);

  useEffect(() => {
    setIsVisible(true);
    const timeout = setTimeout(() => setIsVisible(false), QR_VISIBLE_MS);

    return () => clearTimeout(timeout);
  }, [url]);

  if (!isVisible) return null;

  return (
    <div className="flex flex-col items-center gap-1 rounded-xl border border-white/20 bg-white p-2 shadow-lg">
      {qrSrc ? (
        <img
          src={qrSrc}
          alt="QR code untuk link"
          className="h-32 w-32 rounded-md"
          loading="lazy"
        />
      ) : (
        <div className="flex h-32 w-32 items-center justify-center rounded-md bg-gray-100 text-[10px] font-semibold text-gray-400">
          QR
        </div>
      )}
      <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">
        Scan QR
      </span>
    </div>
  );
}

export default function LiveCaption({
  text,
  isLoading = false,
  avatarState = "idle",
}) {
  const [displayedWords, setDisplayedWords] = useState([]);
  const wordIndexRef = useRef(0);
  const intervalRef = useRef(null);

  // Reset saat text berubah
  useEffect(() => {
    wordIndexRef.current = 0;
    setDisplayedWords([]);

    if (!text || isLoading) return;

    const captionSource = removeLinks(text);
    if (!captionSource) return;

    // Split text jadi kata-kata
    const words = captionSource.split(/\s+/).filter((w) => w.length > 0);
    if (words.length === 0) return;

    // Tampilkan kata per kata dengan interval 150ms
    intervalRef.current = setInterval(() => {
      wordIndexRef.current++;
      if (wordIndexRef.current > words.length) {
        clearInterval(intervalRef.current);
        return;
      }
      setDisplayedWords(words.slice(0, wordIndexRef.current));
    }, 150);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [text, isLoading]);

  // Hide saat bukan speaking mode
  if (avatarState !== "speaking") {
    return null;
  }

  const captionText = displayedWords.join(" ");
  const links = extractLinks(text);

  return (
    <div className="w-full flex justify-center px-4 py-3 animate-fade-in">
      <div className="w-full max-w-md flex flex-col items-center gap-3">
        {isLoading ? (
          // Loading indicator — 3 animated dots
          <div className="flex gap-1.5 items-center justify-center h-6 px-1">
            <span className="w-2 h-2 rounded-full bg-white/70 animate-bounce [animation-delay:-0.3s]" />
            <span className="w-2 h-2 rounded-full bg-white/70 animate-bounce [animation-delay:-0.15s]" />
            <span className="w-2 h-2 rounded-full bg-white/70 animate-bounce" />
          </div>
        ) : captionText ? (
          // Live caption — YouTube-style subtitle
          <div className="text-center">
            <p
              className="text-white text-sm font-medium leading-tight 
              bg-black/60 backdrop-blur-sm px-4 py-2 rounded-lg
              max-h-[3.5rem] overflow-hidden line-clamp-2"
            >
              {captionText}
            </p>
          </div>
        ) : null}

        {links.length > 0 && (
          <div className="flex flex-wrap justify-center gap-2">
            {links.map((url, index) => (
              <TimedQrCard key={`${url}-${index}`} url={url} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
