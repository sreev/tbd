import test from "node:test";
import assert from "node:assert/strict";
import { appendFinalTranscript, formatDuration } from "../src/transcript.js";

test("appends recognized phrases cleanly", () => {
  assert.equal(appendFinalTranscript("Hello", " there. "), "Hello there.");
  assert.equal(appendFinalTranscript("", "A sample sentence."), "A sample sentence.");
});

test("ignores blank recognition results", () => {
  assert.equal(appendFinalTranscript("Keep this", "  "), "Keep this");
  assert.equal(appendFinalTranscript("  ", null), "");
});

test("formats audio duration as minutes and seconds", () => {
  assert.equal(formatDuration(0), "00:00");
  assert.equal(formatDuration(65000), "01:05");
  assert.equal(formatDuration(-1), "00:00");
});
