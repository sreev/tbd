export function appendFinalTranscript(previous, phrase) {
  const cleanPhrase = String(phrase ?? "").trim();
  if (!cleanPhrase) return String(previous ?? "").trim();
  return [String(previous ?? "").trim(), cleanPhrase].filter(Boolean).join(" ");
}

export function formatDuration(milliseconds) {
  const totalSeconds = Math.max(0, Math.floor(Number(milliseconds || 0) / 1000));
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, "0");
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}
