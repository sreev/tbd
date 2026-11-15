import { appendFinalTranscript } from "./transcript.js";
import { recordingStore } from "./storage.js";

const $ = selector => document.querySelector(selector);
const startButton = $("#start");
const stopButton = $("#stop");
const status = $("#status");
const transcript = $("#transcript");
const recordingList = $("#recordings");
const language = $("#language");
const wstStatus = $("#wst-status");
const wstContext = $("#wst-context");
const wstHistory = $("#wst-history");
const wstResults = $("#wst-results");
const wsexResults = $("#wsex-results");
let mediaRecorder;
let chunks = [];
let sessionStarted = 0;
let recordingPromise = null;

function setStatus(message, state = "ready") {
  status.textContent = message;
  status.dataset.state = state;
}

async function refreshRecordings() {
  try {
    const recordings = (await recordingStore.all()).sort((a, b) => b.createdAt - a.createdAt);
    recordingList.replaceChildren();
    if (!recordings.length) {
      recordingList.innerHTML = '<p class="empty">Recordings you save will appear here.</p>';
      return;
    }
    for (const item of recordings) {
      const card = document.createElement("article");
      card.className = "recording-card";
      const heading = document.createElement("div");
      heading.className = "recording-heading";
      const title = document.createElement("strong");
      title.textContent = item.title;
      const date = document.createElement("time");
      date.textContent = new Date(item.createdAt).toLocaleString();
      heading.append(title, date);
      const fileNote = document.createElement("p");
      fileNote.className = "file-note";
      fileNote.textContent = item.filesSaved ? `Files: recordings/${item.filesAudio} + ${item.filesText}` : "Browser copy saved";
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = URL.createObjectURL(item.audio);
      const words = document.createElement("p");
      words.className = "saved-transcript";
      words.textContent = item.transcript || "No transcript captured.";
      const actions = document.createElement("div");
      actions.className = "recording-actions";
      const download = document.createElement("a");
      download.href = audio.src;
      const audioType = (item.audio.type || "audio/webm").split(";", 1)[0];
      const audioExtension = audioType === "audio/mp4" ? "mp4" : audioType === "audio/ogg" ? "ogg" : "webm";
      download.download = `${item.title.replace(/[^\w-]+/g, "-")}.${audioExtension}`;
      download.textContent = "Download audio";
      const copy = document.createElement("button");
      copy.type = "button";
      copy.textContent = "Copy text";
      copy.addEventListener("click", async () => {
        await navigator.clipboard.writeText(item.transcript || "");
        copy.textContent = "Copied";
        setTimeout(() => { copy.textContent = "Copy text"; }, 1400);
      });
      if (!item.transcript) {
        const transcribe = document.createElement("button");
        transcribe.type = "button";
        transcribe.textContent = "Transcribe audio";
        transcribe.addEventListener("click", () => transcribeSavedRecording(item, transcribe));
        actions.append(transcribe);
      } else {
        const search = document.createElement("button");
        search.type = "button";
        search.textContent = "Explore with WST";
        search.addEventListener("click", () => searchWithBoth(item, search, "WST"));
        actions.append(search);
        const exaSearch = document.createElement("button");
        exaSearch.type = "button";
        exaSearch.textContent = "Explore with WSex";
        exaSearch.addEventListener("click", () => searchWithBoth(item, exaSearch, "WSex"));
        actions.append(exaSearch);
      }
      if (!item.filesSaved) {
        const saveFiles = document.createElement("button");
        saveFiles.type = "button";
        saveFiles.textContent = "Save files";
        saveFiles.addEventListener("click", () => saveFilesForItem(item, saveFiles));
        actions.append(saveFiles);
      }
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "quiet-button";
      remove.textContent = "Delete";
      remove.addEventListener("click", async () => {
        if (item.filesSaved) {
          const response = await fetch(`/api/recordings/${encodeURIComponent(item.id)}`, { method: "DELETE" });
          if (!response.ok) {
            setStatus("Could not delete the files from recordings/.", "error");
            return;
          }
        }
        await recordingStore.remove(item.id);
        URL.revokeObjectURL(audio.src);
        await refreshRecordings();
      });
      actions.append(download, copy, remove);
      card.append(heading, fileNote, audio, words, actions);
      recordingList.append(card);
    }
  } catch (error) {
    console.error(error);
    recordingList.innerHTML = '<p class="empty">Local recording storage is unavailable in this browser.</p>';
  }
}

async function blobToBase64(audio) {
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Could not read the recorded audio."));
    reader.readAsDataURL(audio);
  });
  return dataUrl.split(",")[1];
}

async function saveRecordingFiles(recording, transcriptText = recording.transcript || "") {
  const response = await fetch("/api/recordings/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      recordingId: recording.id,
      audioBase64: await blobToBase64(recording.audio),
      mimeType: recording.audio.type || "audio/webm",
      transcript: transcriptText
    })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Saving files failed (HTTP ${response.status}).`);
  return { ...recording, filesSaved: true, filesBase: result.base_name, filesAudio: result.audio_file, filesText: result.transcript_file, transcriptFileSaved: Boolean(transcriptText) };
}

async function saveTranscriptFile(recording, transcriptText) {
  const response = await fetch("/api/recordings/transcript", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recordingId: recording.id, transcript: transcriptText })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Saving transcript file failed (HTTP ${response.status}).`);
  return result.transcript_file;
}

async function transcribeAudio(audio) {
  const response = await fetch("/api/transcribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      audioBase64: await blobToBase64(audio),
      mimeType: audio.type || "audio/webm",
      language: language.value
    })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Transcription failed (HTTP ${response.status}).`);
  return appendFinalTranscript("", result.text);
}

async function transcribeSavedRecording(item, button) {
  button.disabled = true;
  button.textContent = "Transcribing…";
  setStatus("Sending saved audio to Cartesia for transcription…", "recording");
  try {
    let saved = item;
    if (!saved.filesSaved) saved = await saveRecordingFiles(saved);
    const text = await transcribeAudio(saved.audio);
    await saveTranscriptFile(saved, text);
    saved = { ...saved, transcript: text, transcriptFileSaved: Boolean(text) };
    await recordingStore.save(saved);
    transcript.textContent = text || "Cartesia returned an empty transcript. Try recording again, closer to the microphone.";
    setStatus(text ? "Transcript saved with the recording." : "Cartesia returned an empty transcript.", text ? "ready" : "error");
    await refreshRecordings();
  } catch (error) {
    console.error(error);
    setStatus(error.message, "error");
    button.disabled = false;
    button.textContent = "Retry transcription";
  }
}

async function saveFilesForItem(item, button) {
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    const saved = await saveRecordingFiles(item, item.transcript || "");
    await recordingStore.save(saved);
    setStatus("Audio and transcript files saved in recordings/.", "ready");
    await refreshRecordings();
  } catch (error) {
    setStatus(`Could not save files: ${error.message}`, "error");
    button.disabled = false;
    button.textContent = "Retry save";
  }
}

function renderProviderSearch(search, container) {
  container.replaceChildren();
  const heading = document.createElement("div");
  heading.className = "wst-query-row";
  const title = document.createElement("h3");
  title.textContent = search.query;
  const stamp = document.createElement("time");
  stamp.textContent = new Date(search.created_at).toLocaleString();
  heading.append(title, stamp);
  container.append(heading);

  if (search.answer) {
    const answer = document.createElement("div");
    answer.className = "wst-answer";
    const label = document.createElement("span");
    label.textContent = "RESEARCH SUMMARY";
    const copy = document.createElement("p");
    copy.textContent = search.answer;
    answer.append(label, copy);
    container.append(answer);
  }

  if (search.images?.length) {
    const imageHeading = document.createElement("h4");
    imageHeading.className = "wst-subhead";
    imageHeading.textContent = "Visual results";
    container.append(imageHeading);
    const images = document.createElement("div");
    images.className = "wst-images";
    for (const image of search.images) {
      if (!image.url?.startsWith("https://")) continue;
      const link = document.createElement("a");
      link.href = image.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.className = "wst-image-card";
      const preview = document.createElement("img");
      preview.src = image.url;
      preview.alt = image.description || "Search result";
      preview.loading = "lazy";
      const caption = document.createElement("span");
      caption.textContent = image.description || "Open image";
      link.append(preview, caption);
      images.append(link);
    }
    container.append(images);
  }

  const resultHeading = document.createElement("h4");
  resultHeading.className = "wst-subhead";
  resultHeading.textContent = `Sources · ${search.results?.length || 0}`;
  container.append(resultHeading);
  const sources = document.createElement("div");
  sources.className = "wst-sources";
  for (const result of search.results || []) {
    const article = document.createElement("article");
    article.className = "wst-source-card";
    const sourceLink = document.createElement("a");
    sourceLink.href = result.url;
    sourceLink.target = "_blank";
    sourceLink.rel = "noopener noreferrer";
    sourceLink.textContent = result.title || result.url;
    const snippet = document.createElement("p");
    snippet.textContent = result.content || "";
    const domain = document.createElement("span");
    try { domain.textContent = new URL(result.url).hostname; } catch { domain.textContent = result.url || ""; }
    article.append(sourceLink, snippet, domain);
    sources.append(article);
  }
  if (!sources.childElementCount) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No sources were returned for this transcript.";
    sources.append(empty);
  }
  container.append(sources);
}

function renderProviderError(message, container, provider) {
  container.replaceChildren();
  const error = document.createElement("p");
  error.className = "provider-error";
  error.textContent = `${provider}: ${message}`;
  container.append(error);
}

async function loadSearchComparison(searchId) {
  const response = await fetch(`/api/search/both/${encodeURIComponent(searchId)}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Could not load saved comparison.");
  const wstMissing = result.wst_error === "Saved WST search was not found.";
  const wsexMissing = result.wsex_error === "Saved WSex search was not found.";
  if (result.wst && !result.wst.error) renderProviderSearch(result.wst, wstResults);
  else if (wstMissing) renderProviderNotice("No Tavily result was saved for this comparison yet.", wstResults);
  else renderProviderError(result.wst?.error || result.wst_error || "No saved results for this search.", wstResults, "WST");
  if (result.wsex && !result.wsex.error) renderProviderSearch(result.wsex, wsexResults);
  else if (wsexMissing) renderProviderNotice("No Exa result was saved for this earlier WST search. Choose either Explore button on a recording to run both providers.", wsexResults);
  else renderProviderError(result.wsex?.error || result.wsex_error || "No saved results for this search.", wsexResults, "WSex");
  if (wsexMissing) wstStatus.textContent = "Showing an earlier WST-only search. Start a new comparison to add Exa results.";
}

function renderProviderNotice(message, container) {
  container.replaceChildren();
  const notice = document.createElement("p");
  notice.className = "provider-notice";
  notice.textContent = message;
  container.append(notice);
}

async function loadSearchContext() {
  try {
    const response = await fetch("/api/search/context");
    if (!response.ok) throw new Error("Search context is unavailable.");
    const context = await response.json();
    const byId = new Map();
    for (const entry of [...(context.wst.searches || []), ...(context.wsex.searches || [])]) {
      const current = byId.get(entry.id) || { ...entry, providers: [] };
      current.providers.push(entry.agent || (context.wst.searches.includes(entry) ? "WST" : "WSex"));
      current.result_count = Math.max(current.result_count || 0, entry.result_count || 0);
      current.image_count = Math.max(current.image_count || 0, entry.image_count || 0);
      byId.set(entry.id, current);
    }
    const history = [...byId.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
    const readyProviders = [context.providers?.wst ? "Tavily ready" : "Tavily key missing", context.providers?.wsex ? "Exa ready" : "Exa key missing"];
    wstContext.textContent = `${history.length} saved comparison${history.length === 1 ? "" : "s"} · ${readyProviders.join(" · ")} · Context saved locally`;
    wstHistory.replaceChildren();
    for (const item of history) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "wst-history-item";
      const query = document.createElement("strong");
      query.textContent = item.query;
      const counts = document.createElement("span");
      counts.textContent = `${item.providers.join(" + ")} · ${new Date(item.created_at).toLocaleDateString()}`;
      button.append(query, counts);
      button.addEventListener("click", async () => {
        try { await loadSearchComparison(item.id); } catch (error) { wstStatus.textContent = error.message; }
      });
      wstHistory.append(button);
    }
    const activeSearchId = history[0]?.id;
    if (activeSearchId) await loadSearchComparison(activeSearchId);
  } catch (error) {
    wstContext.textContent = "Search history will be saved on this device.";
    wstStatus.textContent = error.message;
  }
}

async function searchWithBoth(item, button, launchedFrom) {
  button.disabled = true;
  button.textContent = "Searching…";
  wstStatus.textContent = `${launchedFrom} started both searches from the saved transcript…`;
  try {
    let saved = item;
    if (!saved.filesSaved) {
      saved = await saveRecordingFiles(saved, saved.transcript || "");
      await recordingStore.save(saved);
    } else if (!saved.transcriptFileSaved && saved.transcript) {
      await saveTranscriptFile(saved, saved.transcript);
      saved = { ...saved, transcriptFileSaved: true };
      await recordingStore.save(saved);
    }
    const response = await fetch("/api/search/both", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recordingId: saved.id })
    });
    const result = await response.json();
    const wstOk = Boolean(result.wst && !result.wst.error);
    const wsexOk = Boolean(result.wsex && !result.wsex.error);
    if (wstOk) renderProviderSearch(result.wst, wstResults);
    else renderProviderError(result.wst?.error || "Search failed.", wstResults, "WST");
    if (wsexOk) renderProviderSearch(result.wsex, wsexResults);
    else renderProviderError(result.wsex?.error || "Search failed.", wsexResults, "WSex");
    if (!response.ok) throw new Error("Both provider searches failed. Check their API keys and retry.");
    wstStatus.textContent = wstOk && wsexOk
      ? `Both result sets saved under comparison ${result.comparison_id}.`
      : `Partial results saved under comparison ${result.comparison_id}; one provider needs attention.`;
    await loadSearchContext();
    await refreshRecordings();
    document.querySelector("#wst-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    wstStatus.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = `Explore with ${launchedFrom}`;
  }
}

async function start() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find(type => MediaRecorder.isTypeSupported(type));
    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    chunks = [];
    transcript.textContent = "Recording… Your transcript will appear after you stop.";
    sessionStarted = Date.now();
    mediaRecorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    recordingPromise = new Promise(resolve => {
      mediaRecorder.onstop = () => resolve(new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" }));
    });
    mediaRecorder.start(500);
    setStatus("Recording. Press Stop & save when you finish; Cartesia will transcribe the saved audio.", "recording");
    startButton.disabled = true;
    stopButton.disabled = false;
  } catch (error) {
    console.error(error);
    setStatus(error.name === "NotAllowedError" ? "Allow microphone access to start recording." : "Could not open the microphone. Check your device and browser permissions.", "error");
  }
}

async function stop() {
  if (!mediaRecorder || mediaRecorder.state === "inactive") return;
  stopButton.disabled = true;
  startButton.disabled = true;
  const endedAt = Date.now();
  mediaRecorder.stop();
  mediaRecorder.stream.getTracks().forEach(track => track.stop());
  const audio = await recordingPromise;
  if (audio.size) {
    const createdAt = new Date().toISOString();
    const title = `Speech ${new Date(createdAt).toLocaleString()}`;
    const recording = { id: crypto.randomUUID(), title, createdAt: Date.parse(createdAt), duration: endedAt - sessionStarted, transcript: "", audio, filesSaved: false };
    await recordingStore.save(recording);
    let filesSaveError = "";
    try {
      Object.assign(recording, await saveRecordingFiles(recording));
      await recordingStore.save(recording);
    } catch (error) {
      filesSaveError = error.message;
    }
    transcript.textContent = "Transcribing your recording with Cartesia…";
    setStatus("Audio saved locally. Sending it to Cartesia for transcription…", "recording");
    try {
      recording.transcript = await transcribeAudio(audio);
      if (recording.filesSaved) {
        await saveTranscriptFile(recording, recording.transcript);
        recording.transcriptFileSaved = Boolean(recording.transcript);
      }
      transcript.textContent = recording.transcript || "Cartesia returned an empty transcript. Try speaking closer to the microphone.";
      setStatus(filesSaveError ? `Transcribed and saved in browser. Folder copy failed: ${filesSaveError}` : recording.transcript ? "Audio and transcript saved in recordings/." : "Cartesia returned an empty transcript.", filesSaveError || !recording.transcript ? "error" : "ready");
    } catch (error) {
      console.error(error);
      transcript.textContent = `Transcription failed: ${error.message}`;
      setStatus("Audio was saved. Transcription failed; retry it from Saved recordings.", "error");
    }
    await recordingStore.save(recording);
    await refreshRecordings();
  } else {
    setStatus("No audio was captured. Check your microphone and try again.", "error");
  }
  startButton.disabled = false;
  stopButton.disabled = true;
  mediaRecorder = null;
}

startButton.addEventListener("click", start);
stopButton.addEventListener("click", stop);
refreshRecordings();
loadSearchContext();
