/**
 * app.js — YT Downloader Frontend
 *
 * Handles UI interactions, API communication, job polling, and DOM updates.
 * No frameworks. Uses Fetch API and vanilla DOM manipulation.
 */

(function () {
  'use strict';

  // =========================================================================
  // Configuration
  // =========================================================================

  // Base API configuration (configurable for GitHub Pages / Render)
  const API_BASE = (function () {
    if (window.API_BASE_URL) return window.API_BASE_URL.replace(/\/+$/, '');
    try {
      const saved = localStorage.getItem('ytdl_backend_url');
      if (saved) return saved.replace(/\/+$/, '');
    } catch (_) {}
    if (
      window.location.hostname.includes('github.io') ||
      window.location.hostname.includes('pages.dev') ||
      window.location.hostname.includes('cloudflare') ||
      (!['localhost', '127.0.0.1', ''].includes(window.location.hostname))
    ) {
      return 'https://yt-downloader-backend-n68l.onrender.com';
    }
    return '';
  })();

  const API = {
    BASE: API_BASE,
    HEALTH: `${API_BASE}/api/health`,
    METADATA: `${API_BASE}/api/metadata`,
    STREAM_URL: `${API_BASE}/api/stream-url`,
    DOWNLOADS: `${API_BASE}/api/downloads`,
    BATCHES: `${API_BASE}/api/batches`,
    JOBS: `${API_BASE}/api/jobs`,
  };

  const POLL_INTERVAL_ACTIVE = 2000;   // 2s for active jobs
  const POLL_INTERVAL_IDLE = 10000;    // 10s when all jobs are terminal
  const TOAST_DURATION = 5000;
  const MAX_POLL_ERRORS = 5;

  // YouTube URL pattern (client-side pre-validation only)
  const YT_URL_REGEX = /^https?:\/\/(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?|shorts\/|embed\/|v\/|playlist\?)|youtu\.be\/|music\.youtube\.com\/)/i;

  // LocalStorage / Browser Cache keys for history & permission
  const STORAGE_KEYS = {
    PERMISSION: 'ytdl_save_history_enabled',
    HISTORY: 'ytdl_video_history',
    TOS_ACCEPTED: 'ytdl_tos_accepted',
  };

  // =========================================================================
  // State
  // =========================================================================

  const state = {
    activeTab: 'single',
    formatType: 'audio',
    bulkFormatType: 'audio',
    playlistMode: 'playlist', // 'playlist' or 'video'
    lastFetchedMeta: null,
    jobs: new Map(),          // job_id -> job data
    sessionJobIds: new Set(), // Job IDs created in this session
    pollingTimer: null,
    pollErrors: 0,
    isSubmitting: false,
    isFetchingMeta: false,
    // Structured batch state
    bulkBatchLimit: 20,
    bulkQueueLimit: 50,
    bulkChunkSize: 20,
    structuredBatches: [],
    autoQueueActive: false,
    autoQueuePaused: false,
    autoQueueSubmitting: false,
    isBatchListOpen: false,
    autoQueueRetryTimer: null,
  };

  // =========================================================================
  // DOM References
  // =========================================================================

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    // Health
    statusDot: $('#status-dot'),
    statusText: $('#status-text'),

    // Tabs
    tabSingle: $('#tab-single'),
    tabBulk: $('#tab-bulk'),
    panelSingle: $('#panel-single'),
    panelBulk: $('#panel-bulk'),

    // Single download
    urlInput: $('#url-input'),
    urlFeedback: $('#url-feedback'),
    btnFetchMeta: $('#btn-fetch-meta'),
    metaPreview: $('#meta-preview'),
    metaThumb: $('#meta-thumb'),
    metaTitle: $('#meta-title'),
    metaDetail: $('#meta-detail'),
    playlistOptions: $('#playlist-options'),
    playlistOptionsTitle: $('#playlist-options-title'),
    modePlaylist: $('#mode-playlist'),
    modeSingle: $('#mode-single'),
    qualitySelect: $('#quality-select'),
    fmtVideo: $('#fmt-video'),
    fmtAudio: $('#fmt-audio'),
    audioOptions: $('#audio-options'),
    audioFormatSelect: $('#audio-format-select'),
    btnDownload: $('#btn-download'),

    // Bulk download
    bulkInput: $('#bulk-input'),
    bulkFeedback: $('#bulk-feedback'),
    bulkSummary: $('#bulk-summary'),
    bulkValid: $('#bulk-valid'),
    bulkInvalid: $('#bulk-invalid'),
    bulkDupes: $('#bulk-dupes'),
    bulkQualitySelect: $('#bulk-quality-select'),
    bulkFmtVideo: $('#bulk-fmt-video'),
    bulkFmtAudio: $('#bulk-fmt-audio'),
    btnBulkDownload: $('#btn-bulk-download'),
    btnBulkDownloadText: $('#btn-bulk-download-text'),
    bulkLimitHint: $('#bulk-limit-hint'),

    // Structured batch assistant
    bulkBatchAssistant: $('#bulk-batch-assistant'),
    batchOrchestratorStatus: $('#batch-orchestrator-status'),
    batchTotalCount: $('#batch-total-count'),
    batchCountIndicator: $('#batch-count-indicator'),
    batchSizeIndicator: $('#batch-size-indicator'),
    metricTotalUrls: $('#metric-total-urls'),
    metricTotalBatches: $('#metric-total-batches'),
    metricBatchProgress: $('#metric-batch-progress'),
    batchSizeSelect: $('#batch-size-select'),
    batchLiveProgress: $('#batch-live-progress'),
    batchLiveProgressTitle: $('#batch-live-progress-title'),
    batchLiveProgressStats: $('#batch-live-progress-stats'),
    batchLiveProgressBar: $('#batch-live-progress-bar'),
    btnBatchAutoAll: $('#btn-batch-auto-all'),
    btnBatchAutoText: $('#btn-batch-auto-text'),
    btnBatchDownloadFirst: $('#btn-batch-download-first'),
    btnBatchToggleList: $('#btn-batch-toggle-list'),
    batchListCount: $('#batch-list-count'),
    btnBatchPause: $('#btn-batch-pause'),
    btnBatchCancel: $('#btn-batch-cancel'),
    batchItemsContainer: $('#batch-items-container'),
    batchItemsList: $('#batch-items-list'),

    // Jobs & History
    activeCount: $('#active-count'),
    jobsList: $('#jobs-list'),
    emptyState: $('#empty-state'),
    emptyStateText: $('#empty-state-text'),
    emptyStateHint: $('#empty-state-hint'),
    toggleHistoryStorage: $('#toggle-history-storage'),
    storageStatusBadge: $('#storage-status-badge'),
    btnClearHistory: $('#btn-clear-history'),

    // Toast
    toastContainer: $('#toast-container'),

    // ToS
    tosCheckSingle: $('#tos-check-single'),
    tosCheckBulk: $('#tos-check-bulk'),
    tosBarSingle: $('#tos-bar-single'),
    tosBarBulk: $('#tos-bar-bulk'),
  };

  // =========================================================================
  // Initialization
  // =========================================================================

  function init() {
    bindEvents();
    initToS();
    checkHealth();
    loadJobs();
    setInterval(checkHealth, 30000);
    // Default to audio mode on load
    setFormat('audio');
    setBulkFormat('audio');
  }

  // =========================================================================
  // Event Binding
  // =========================================================================

  function bindEvents() {
    // Tabs
    dom.tabSingle.addEventListener('click', () => switchTab('single'));
    dom.tabBulk.addEventListener('click', () => switchTab('bulk'));

    // Single URL input
    dom.urlInput.addEventListener('input', debounce(validateSingleUrl, 300));
    dom.urlInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') dom.btnDownload.click();
    });

    // Metadata fetch
    dom.btnFetchMeta.addEventListener('click', fetchMetadata);

    // Playlist mode toggles
    if (dom.modePlaylist) {
      dom.modePlaylist.addEventListener('click', () => setPlaylistMode('playlist'));
    }
    if (dom.modeSingle) {
      dom.modeSingle.addEventListener('click', () => setPlaylistMode('video'));
    }

    // Format toggle (single)
    dom.fmtVideo.addEventListener('click', () => setFormat('video'));
    dom.fmtAudio.addEventListener('click', () => setFormat('audio'));

    // Download button
    dom.btnDownload.addEventListener('click', submitSingleDownload);

    // Bulk input
    dom.bulkInput.addEventListener('input', debounce(validateBulkUrls, 500));

    // Format toggle (bulk)
    dom.bulkFmtVideo.addEventListener('click', () => setBulkFormat('video'));
    dom.bulkFmtAudio.addEventListener('click', () => setBulkFormat('audio'));

    // Bulk download button
    dom.btnBulkDownload.addEventListener('click', submitBulkDownload);

    // Structured Batch Assistant events
    if (dom.btnBatchAutoAll) {
      dom.btnBatchAutoAll.addEventListener('click', startAutoBatchProcessing);
    }
    if (dom.btnBatchDownloadFirst) {
      dom.btnBatchDownloadFirst.addEventListener('click', downloadFirstBatch);
    }
    if (dom.btnBatchToggleList) {
      dom.btnBatchToggleList.addEventListener('click', toggleBatchList);
    }
    if (dom.btnBatchPause) {
      dom.btnBatchPause.addEventListener('click', togglePauseAutoBatch);
    }
    if (dom.btnBatchCancel) {
      dom.btnBatchCancel.addEventListener('click', cancelAutoBatch);
    }
    if (dom.batchSizeSelect) {
      dom.batchSizeSelect.addEventListener('change', handleBatchSizeChange);
    }

    // History storage controls
    if (dom.toggleHistoryStorage) {
      dom.toggleHistoryStorage.addEventListener('change', handleStorageToggle);
    }
    if (dom.btnClearHistory) {
      dom.btnClearHistory.addEventListener('click', handleClearHistory);
    }

    // ToS checkboxes
    if (dom.tosCheckSingle) {
      dom.tosCheckSingle.addEventListener('change', () => handleTosCheck('single'));
    }
    if (dom.tosCheckBulk) {
      dom.tosCheckBulk.addEventListener('change', () => handleTosCheck('bulk'));
    }
  }

  // =========================================================================
  // Terms of Service Agreement
  // =========================================================================

  function initToS() {
    let alreadyAccepted = true;
    try {
      const stored = localStorage.getItem(STORAGE_KEYS.TOS_ACCEPTED);
      if (stored === 'false') alreadyAccepted = false;
    } catch (_) {}

    _setTosState(alreadyAccepted);
  }

  function handleTosCheck(panel) {
    // Sync both checkboxes — accepting in either panel accepts globally
    const checked = panel === 'single'
      ? dom.tosCheckSingle?.checked
      : dom.tosCheckBulk?.checked;

    _setTosState(!!checked);

    if (checked) {
      try { localStorage.setItem(STORAGE_KEYS.TOS_ACCEPTED, 'true'); } catch (_) {}
    } else {
      try { localStorage.removeItem(STORAGE_KEYS.TOS_ACCEPTED); } catch (_) {}
    }
  }

  function _setTosState(accepted) {
    // Sync both checkboxes
    if (dom.tosCheckSingle) dom.tosCheckSingle.checked = accepted;
    if (dom.tosCheckBulk)   dom.tosCheckBulk.checked   = accepted;

    // Toggle bar styling
    if (dom.tosBarSingle) dom.tosBarSingle.classList.toggle('accepted', accepted);
    if (dom.tosBarBulk)   dom.tosBarBulk.classList.toggle('accepted', accepted);

    // Enable / disable download buttons
    if (dom.btnDownload)     dom.btnDownload.disabled     = !accepted;
    if (dom.btnBulkDownload) dom.btnBulkDownload.disabled = !accepted;
  }

  // =========================================================================
  // Tab Switching
  // =========================================================================

  function switchTab(tab) {
    state.activeTab = tab;

    dom.tabSingle.classList.toggle('active', tab === 'single');
    dom.tabBulk.classList.toggle('active', tab === 'bulk');
    dom.tabSingle.setAttribute('aria-selected', tab === 'single');
    dom.tabBulk.setAttribute('aria-selected', tab === 'bulk');

    dom.panelSingle.classList.toggle('active', tab === 'single');
    dom.panelBulk.classList.toggle('active', tab === 'bulk');
    dom.panelSingle.hidden = tab !== 'single';
    dom.panelBulk.hidden = tab !== 'bulk';
  }

  // =========================================================================
  // Format Toggle
  // =========================================================================

  function setFormat(type) {
    state.formatType = type;
    dom.fmtVideo.classList.toggle('active', type === 'video');
    dom.fmtAudio.classList.toggle('active', type === 'audio');
    dom.fmtVideo.setAttribute('aria-checked', type === 'video');
    dom.fmtAudio.setAttribute('aria-checked', type === 'audio');

    // Show/hide audio sub-options
    if (dom.audioOptions) dom.audioOptions.classList.toggle('hidden', type !== 'audio');

    // Show/hide server warning notice for video
    const notice = document.getElementById('video-server-notice');
    if (notice) notice.style.display = type === 'video' ? 'flex' : 'none';

    // Show/hide video quality row
    const vqRow = document.getElementById('video-quality-row');
    if (vqRow) vqRow.style.display = type === 'video' ? 'block' : 'none';

    // Update button text
    const btnText = dom.btnDownload?.querySelector('.btn__text');
    if (btnText) {
      btnText.textContent = type === 'audio' ? '⬇ Download Audio' : '⬇ Download Video';
    }

    // Keep legacy quality-select (hidden) in sync with video-quality-select-v
    const vqSel = document.getElementById('quality-select-v');
    if (vqSel && dom.qualitySelect) {
      vqSel.addEventListener('change', () => { dom.qualitySelect.value = vqSel.value; }, { once: false });
      if (type === 'video') dom.qualitySelect.value = vqSel.value;
    }

    // Hide legacy quality group (was inside options-row, now replaced)
    if (dom.qualitySelect) dom.qualitySelect.closest('.form-group')?.classList.add('hidden');
  }

  function setBulkFormat(type) {
    state.bulkFormatType = type;
    dom.bulkFmtVideo.classList.toggle('active', type === 'video');
    dom.bulkFmtAudio.classList.toggle('active', type === 'audio');
    dom.bulkFmtVideo.setAttribute('aria-checked', type === 'video');
    dom.bulkFmtAudio.setAttribute('aria-checked', type === 'audio');

    const bulkBtnText = document.getElementById('btn-bulk-download-text');
    if (bulkBtnText) {
      bulkBtnText.textContent = type === 'audio' ? '⬇ Download All Audio (Batch)' : '⬇ Download All Videos';
    }
  }

  // =========================================================================
  // Health Check
  // =========================================================================

  async function checkHealth() {
    try {
      const resp = await fetchAPI(API.HEALTH);
      if (resp.success) {
        dom.statusDot.className = 'status-dot healthy';
        const d = resp.data;
        if (window.innerWidth <= 480) {
          dom.statusText.textContent = d.active_jobs > 0 ? `${d.active_jobs} active` : 'Online';
        } else {
          dom.statusText.textContent = `${d.active_jobs} active · ${d.queued_jobs} queued`;
        }
        if (d.max_batch_size) state.bulkBatchLimit = Number(d.max_batch_size);
        if (d.max_queue_depth) state.bulkQueueLimit = Number(d.max_queue_depth);
      } else {
        setUnhealthy();
      }
    } catch {
      setUnhealthy();
    }
  }

  function setUnhealthy() {
    dom.statusDot.className = 'status-dot unhealthy';
    dom.statusText.textContent = 'Offline';
  }

  // =========================================================================
  // URL Validation (Client-side)
  // =========================================================================

  function getYouTubeThumbnail(url) {
    if (!url) return null;
    const match = url.match(/(?:v=|\/embed\/|\/shorts\/|\/v\/|youtu\.be\/|\/watch\?v=|\/watch\?.+&v=)([\w-]{11})/i);
    if (match && match[1]) {
      return `https://i.ytimg.com/vi/${match[1]}/mqdefault.jpg`;
    }
    return null;
  }

  function setPlaylistMode(mode) {
    state.playlistMode = mode;
    if (dom.modePlaylist) {
      dom.modePlaylist.classList.toggle('active', mode === 'playlist');
      dom.modePlaylist.setAttribute('aria-checked', mode === 'playlist');
    }
    if (dom.modeSingle) {
      dom.modeSingle.classList.toggle('active', mode === 'video');
      dom.modeSingle.setAttribute('aria-checked', mode === 'video');
    }
    const btnText = dom.btnDownload?.querySelector('.btn__text');
    if (btnText && !state.isSubmitting) {
      btnText.textContent = mode === 'playlist' ? 'Download Playlist' : 'Download Video';
    }
  }

  function validateSingleUrl() {
    const url = dom.urlInput.value.trim();
    if (!url) {
      setFeedback(dom.urlFeedback, '', '');
      dom.urlInput.classList.remove('error', 'success');
      dom.metaPreview.classList.add('hidden');
      if (dom.playlistOptions) dom.playlistOptions.classList.add('hidden');
      return false;
    }

    if (!YT_URL_REGEX.test(url)) {
      setFeedback(dom.urlFeedback, 'Please enter a valid YouTube URL.', 'error');
      dom.urlInput.classList.add('error');
      dom.urlInput.classList.remove('success');
      if (dom.playlistOptions) dom.playlistOptions.classList.add('hidden');
      return false;
    }

    setFeedback(dom.urlFeedback, '✓ Valid YouTube URL', 'success');
    dom.urlInput.classList.add('success');
    dom.urlInput.classList.remove('error');

    const hasPlaylist = /[?&]list=([a-zA-Z0-9_-]+)/i.test(url) || url.includes('/playlist?');
    if (dom.playlistOptions) {
      if (hasPlaylist) {
        dom.playlistOptions.classList.remove('hidden');
        if (dom.playlistOptionsTitle) {
          dom.playlistOptionsTitle.textContent = 'Playlist detected. Choose download mode:';
        }
        setPlaylistMode(state.playlistMode || 'playlist');
      } else {
        dom.playlistOptions.classList.add('hidden');
        const btnText = dom.btnDownload?.querySelector('.btn__text');
        if (btnText && !state.isSubmitting) {
          btnText.textContent = 'Download';
        }
      }
    }

    return true;
  }

  function validateBulkUrls() {
    const text = dom.bulkInput.value.trim();
    if (!text) {
      dom.bulkSummary.classList.add('hidden');
      setFeedback(dom.bulkFeedback, '', '');
      updateBatchAssistant([]);
      return { valid: [], invalid: [], duplicates: 0 };
    }

    const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
    const valid = [];
    const invalid = [];
    const seen = new Set();
    let duplicates = 0;

    for (const line of lines) {
      if (YT_URL_REGEX.test(line)) {
        if (seen.has(line)) {
          duplicates++;
        } else {
          seen.add(line);
          valid.push(line);
        }
      } else {
        invalid.push(line);
      }
    }

    dom.bulkValid.textContent = `${valid.length} valid`;
    dom.bulkInvalid.textContent = `${invalid.length} invalid`;
    dom.bulkDupes.textContent = `${duplicates} duplicates`;
    dom.bulkSummary.classList.remove('hidden');

    if (invalid.length > 0) {
      setFeedback(dom.bulkFeedback, `${invalid.length} URL(s) will be rejected by the server.`, 'error');
    } else {
      setFeedback(dom.bulkFeedback, '', '');
    }

    updateBatchAssistant(valid);
    return { valid, invalid, duplicates };
  }

  // =========================================================================
  // Structured Batch Management (Smart Chunking & Staged Orchestration)
  // =========================================================================

  function chunkArray(arr, size) {
    const chunks = [];
    for (let i = 0; i < arr.length; i += size) {
      chunks.push(arr.slice(i, i + size));
    }
    return chunks;
  }

  function buildStructuredBatches(urls, chunkSize) {
    const chunks = chunkArray(urls, chunkSize);
    return chunks.map((chunk, idx) => {
      const startIdx = idx * chunkSize + 1;
      const endIdx = startIdx + chunk.length - 1;
      return {
        id: `batch-chunk-${idx + 1}`,
        index: idx,
        label: `Batch ${idx + 1}`,
        range: `URLs ${startIdx} – ${endIdx}`,
        urls: chunk,
        status: 'PENDING', // PENDING, QUEUED, RUNNING, COMPLETED, FAILED
        jobIds: [],
      };
    });
  }

  function updateBatchAssistant(validUrls) {
    if (!dom.bulkBatchAssistant) return;

    if (validUrls.length > state.bulkBatchLimit) {
      const totalUrls = validUrls.length;
      const existingQueued = state.structuredBatches.filter((b) => b.status !== 'PENDING');

      // If we are not actively in auto-queue and have no running batches, build fresh
      if (!state.autoQueueActive && existingQueued.length === 0) {
        state.structuredBatches = buildStructuredBatches(validUrls, state.bulkChunkSize);
      }

      const batches = state.structuredBatches;
      const totalBatches = batches.length;

      // Update Header & Desc
      if (dom.batchTotalCount) dom.batchTotalCount.textContent = totalUrls;
      if (dom.batchCountIndicator) dom.batchCountIndicator.textContent = totalBatches;
      if (dom.batchSizeIndicator) dom.batchSizeIndicator.textContent = state.bulkChunkSize;

      // Update Metrics
      if (dom.metricTotalUrls) dom.metricTotalUrls.textContent = totalUrls;
      if (dom.metricTotalBatches) dom.metricTotalBatches.textContent = totalBatches;
      if (dom.batchListCount) dom.batchListCount.textContent = totalBatches;

      // Update action button texts
      if (dom.btnBatchAutoText) {
        dom.btnBatchAutoText.textContent = `Auto-Queue All ${totalBatches} Batches (1 to ${totalBatches})`;
      }
      if (dom.btnBatchDownloadFirst && batches[0]) {
        dom.btnBatchDownloadFirst.textContent = `⚡ Queue Batch 1 (First ${batches[0].urls.length}) & Keep Remaining`;
      }
      if (dom.btnBulkDownloadText) {
        dom.btnBulkDownloadText.textContent = `Download All in ${totalBatches} Batches (${totalUrls} URLs)`;
      }
      if (dom.bulkLimitHint) {
        dom.bulkLimitHint.textContent = `${totalUrls} URLs detected · Structured into ${totalBatches} batches of up to ${state.bulkChunkSize}`;
      }

      updateBatchProgressUI();
      renderBatchItemsList();
      dom.bulkBatchAssistant.classList.remove('hidden');
    } else {
      if (!state.autoQueueActive) {
        dom.bulkBatchAssistant.classList.add('hidden');
        state.structuredBatches = [];
        if (dom.btnBulkDownloadText) dom.btnBulkDownloadText.textContent = 'Download All';
        if (dom.bulkLimitHint) {
          dom.bulkLimitHint.textContent = 'Standard limit: 20 per batch · Large lists structured automatically';
        }
      }
    }
  }

  function handleBatchSizeChange(e) {
    const newSize = parseInt(e.target.value, 10);
    if (newSize > 0 && newSize <= 20) {
      state.bulkChunkSize = newSize;
      const { valid } = validateBulkUrls();
      if (valid.length > 0) {
        state.structuredBatches = buildStructuredBatches(valid, state.bulkChunkSize);
        updateBatchAssistant(valid);
        showToast(`Batch size set to ${state.bulkChunkSize} URLs per batch.`, 'info');
      }
    }
  }

  function toggleBatchList() {
    state.isBatchListOpen = !state.isBatchListOpen;
    if (dom.batchItemsContainer) {
      dom.batchItemsContainer.classList.toggle('hidden', !state.isBatchListOpen);
    }
    if (dom.btnBatchToggleList) {
      dom.btnBatchToggleList.textContent = state.isBatchListOpen
        ? `Hide Batch List (${state.structuredBatches.length})`
        : `📋 View All Batches (${state.structuredBatches.length})`;
    }
  }

  function renderBatchItemsList() {
    if (!dom.batchItemsList) return;
    const batches = state.structuredBatches;
    if (batches.length === 0) {
      dom.batchItemsList.innerHTML = '';
      return;
    }

    dom.batchItemsList.innerHTML = batches
      .map((b) => {
        let pillClass = 'batch-pill--pending';
        let statusLabel = 'Ready';
        let actionBtn = `<button type="button" class="btn btn--secondary btn--small" onclick="window._queueBatchByIndex(${b.index})">▶ Queue Batch</button>`;

        if (b.status === 'QUEUED') {
          pillClass = 'batch-pill--queued';
          statusLabel = 'Queued';
          actionBtn = `<span class="batch-pill ${pillClass}">Queued</span>`;
        } else if (b.status === 'RUNNING') {
          pillClass = 'batch-pill--running';
          statusLabel = 'Running';
          actionBtn = `<span class="batch-pill ${pillClass}">Running</span>`;
        } else if (b.status === 'COMPLETED') {
          pillClass = 'batch-pill--completed';
          statusLabel = 'Completed';
          actionBtn = `<span class="batch-pill ${pillClass}">✓ Done</span>`;
        } else if (b.status === 'FAILED') {
          pillClass = 'batch-pill--failed';
          statusLabel = 'Failed';
          actionBtn = `<button type="button" class="btn btn--retry btn--small" onclick="window._queueBatchByIndex(${b.index})">🔄 Retry</button>`;
        }

        const previewId = `batch-preview-${b.index}`;
        const escapedUrls = b.urls.map(escapeHtml).join('\n');

        return `
          <div class="batch-item-card ${b.status === 'RUNNING' ? 'is-active' : ''} ${b.status === 'COMPLETED' ? 'is-completed' : ''}" id="batch-item-${b.index}">
            <div class="batch-item-info">
              <div class="batch-item-title">${escapeHtml(b.label)}</div>
              <div class="batch-item-meta">
                <span class="batch-item-range">${escapeHtml(b.range)}</span>
                <span>·</span>
                <span>${b.urls.length} URLs</span>
                <span>·</span>
                <button type="button" class="batch-preview-toggle" onclick="window._toggleBatchPreview(${b.index})">Preview URLs</button>
              </div>
              <div id="${previewId}" class="batch-preview-box hidden">${escapedUrls}</div>
            </div>
            <div class="batch-item-right">
              ${actionBtn}
            </div>
          </div>
        `;
      })
      .join('');
  }

  function updateBatchProgressUI() {
    const batches = state.structuredBatches;
    if (batches.length === 0) return;

    let queuedCount = 0;
    let completedCount = 0;
    let totalCount = 0;

    for (const b of batches) {
      totalCount += b.urls.length;
      if (b.status === 'QUEUED' || b.status === 'RUNNING') {
        queuedCount += b.urls.length;
      } else if (b.status === 'COMPLETED') {
        completedCount += b.urls.length;
        queuedCount += b.urls.length;
      }
    }

    const percent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;
    if (dom.metricBatchProgress) dom.metricBatchProgress.textContent = `${percent}%`;

    if (dom.batchLiveProgressBar) {
      dom.batchLiveProgressBar.style.width = `${percent}%`;
    }
    if (dom.batchLiveProgressStats) {
      dom.batchLiveProgressStats.textContent = `${completedCount} / ${totalCount} URLs completed (${queuedCount} queued)`;
    }
  }

  async function queueBatchByIndex(index) {
    if (index < 0 || index >= state.structuredBatches.length) return false;
    const batch = state.structuredBatches[index];
    if (batch.status === 'QUEUED' || batch.status === 'RUNNING' || batch.status === 'COMPLETED') {
      return false;
    }

    batch.status = 'QUEUED';
    renderBatchItemsList();

    const quality = dom.bulkQualitySelect ? dom.bulkQualitySelect.value : 'best';
    const formatType = state.bulkFormatType || 'video';

    try {
      const resp = await fetchAPI(API.BATCHES, {
        method: 'POST',
        body: JSON.stringify({ urls: batch.urls, quality, format_type: formatType }),
      });

      if (resp.success) {
        const d = resp.data;
        batch.status = 'RUNNING';
        if (d.jobs && Array.isArray(d.jobs)) {
          batch.jobIds = d.jobs.map((j) => j.job_id || j.id).filter(Boolean);
          for (const j of d.jobs) {
            const jid = j.job_id || j.id;
            if (jid) {
              state.sessionJobIds.add(jid);
              state.jobs.set(jid, {
                id: jid,
                url: j.url,
                title: j.title || '',
                thumbnail: j.thumbnail || getYouTubeThumbnail(j.url),
                status: j.status || 'QUEUED',
                quality,
                format_type: formatType,
                created_at: new Date().toISOString(),
              });
            }
          }
        }

        if (isHistoryStorageAllowed()) {
          saveStoredHistory(Array.from(state.jobs.values()));
        }

        renderCurrentJobs();
        updateActiveCount();
        startPolling();
        updateBatchProgressUI();
        renderBatchItemsList();

        showToast(`Batch ${index + 1} (${batch.urls.length} videos) queued!`, 'success');
        return true;
      } else {
        batch.status = 'FAILED';
        renderBatchItemsList();
        showToast(resp.error?.message || `Failed to queue Batch ${index + 1}.`, 'error');
        return false;
      }
    } catch (err) {
      batch.status = 'FAILED';
      renderBatchItemsList();
      showToast(`Network error queueing Batch ${index + 1}.`, 'error');
      return false;
    }
  }

  async function downloadFirstBatch() {
    const { valid } = validateBulkUrls();
    if (valid.length === 0) return;

    if (state.structuredBatches.length === 0) {
      state.structuredBatches = buildStructuredBatches(valid, state.bulkChunkSize);
    }

    const firstBatch = state.structuredBatches[0];
    if (!firstBatch) return;

    const success = await queueBatchByIndex(0);
    if (success) {
      // Remove first batch URLs from textarea so user has remaining links ready
      const remainingUrls = valid.slice(firstBatch.urls.length);
      dom.bulkInput.value = remainingUrls.join('\n');
      validateBulkUrls();

      if (remainingUrls.length > 0) {
        showToast(
          `Batch 1 (20 videos) queued! Remaining ${remainingUrls.length} URLs ready in editor for next batch.`,
          'info'
        );
      }
    }
  }

  async function startAutoBatchProcessing() {
    const { valid } = validateBulkUrls();
    if (valid.length === 0) return;

    if (state.structuredBatches.length === 0) {
      state.structuredBatches = buildStructuredBatches(valid, state.bulkChunkSize);
      updateBatchAssistant(valid);
    }

    state.autoQueueActive = true;
    state.autoQueuePaused = false;

    // Show live progress & pause/stop controls
    if (dom.batchLiveProgress) dom.batchLiveProgress.classList.remove('hidden');
    if (dom.btnBatchPause) {
      dom.btnBatchPause.classList.remove('hidden');
      dom.btnBatchPause.textContent = '⏸ Pause Auto-Queue';
    }
    if (dom.btnBatchCancel) dom.btnBatchCancel.classList.remove('hidden');
    if (dom.btnBatchAutoAll) dom.btnBatchAutoAll.classList.add('hidden');
    if (dom.btnBatchDownloadFirst) dom.btnBatchDownloadFirst.classList.add('hidden');

    if (dom.batchOrchestratorStatus) {
      dom.batchOrchestratorStatus.textContent = 'Auto-Queue Active';
      dom.batchOrchestratorStatus.className = 'batch-assistant__status-pill active';
    }

    showToast(`Starting auto-queue sequence for ${valid.length} URLs in batches...`, 'info');
    processNextAutoBatch();
  }

  function togglePauseAutoBatch() {
    state.autoQueuePaused = !state.autoQueuePaused;
    if (state.autoQueuePaused) {
      if (dom.btnBatchPause) dom.btnBatchPause.textContent = '▶ Resume Auto-Queue';
      if (dom.batchOrchestratorStatus) {
        dom.batchOrchestratorStatus.textContent = 'Auto-Queue Paused';
        dom.batchOrchestratorStatus.className = 'batch-assistant__status-pill';
      }
      showToast('Auto-batch queue paused.', 'info');
    } else {
      if (dom.btnBatchPause) dom.btnBatchPause.textContent = '⏸ Pause Auto-Queue';
      if (dom.batchOrchestratorStatus) {
        dom.batchOrchestratorStatus.textContent = 'Auto-Queue Active';
        dom.batchOrchestratorStatus.className = 'batch-assistant__status-pill active';
      }
      showToast('Auto-batch queue resumed.', 'info');
      processNextAutoBatch();
    }
  }

  function cancelAutoBatch() {
    state.autoQueueActive = false;
    state.autoQueuePaused = false;
    if (state.autoQueueRetryTimer) {
      clearTimeout(state.autoQueueRetryTimer);
      state.autoQueueRetryTimer = null;
    }

    if (dom.btnBatchPause) dom.btnBatchPause.classList.add('hidden');
    if (dom.btnBatchCancel) dom.btnBatchCancel.classList.add('hidden');
    if (dom.btnBatchAutoAll) dom.btnBatchAutoAll.classList.remove('hidden');
    if (dom.btnBatchDownloadFirst) dom.btnBatchDownloadFirst.classList.remove('hidden');

    if (dom.batchOrchestratorStatus) {
      dom.batchOrchestratorStatus.textContent = 'Auto-Queue Stopped';
      dom.batchOrchestratorStatus.className = 'batch-assistant__status-pill';
    }

    showToast('Auto-batch queue stopped.', 'info');
  }

  async function processNextAutoBatch() {
    if (!state.autoQueueActive || state.autoQueuePaused || state.autoQueueSubmitting) return;

    // Find next pending batch
    const nextBatch = state.structuredBatches.find((b) => b.status === 'PENDING');
    if (!nextBatch) {
      // Check if all are queued or finished
      const allQueuedOrDone = state.structuredBatches.every(
        (b) => b.status === 'QUEUED' || b.status === 'RUNNING' || b.status === 'COMPLETED'
      );
      if (allQueuedOrDone) {
        if (dom.batchOrchestratorStatus) {
          dom.batchOrchestratorStatus.textContent = 'All Batches Queued';
          dom.batchOrchestratorStatus.className = 'batch-assistant__status-pill active';
        }
      }
      return;
    }

    // Check active jobs count in current session/server
    let activeCount = 0;
    for (const j of state.jobs.values()) {
      if (j.status === 'QUEUED' || j.status === 'RUNNING') {
        activeCount++;
      }
    }

    // Safety threshold: don't overflow the max queue depth (default 50)
    const queueLimit = state.bulkQueueLimit || 50;
    if (activeCount + nextBatch.urls.length > queueLimit) {
      if (dom.batchOrchestratorStatus) {
        dom.batchOrchestratorStatus.textContent = `Queue Full (${activeCount} active). Waiting...`;
      }
      if (dom.batchLiveProgressTitle) {
        dom.batchLiveProgressTitle.textContent = `Waiting for downloads to finish before starting Batch ${nextBatch.index + 1}...`;
      }
      if (state.autoQueueRetryTimer) clearTimeout(state.autoQueueRetryTimer);
      state.autoQueueRetryTimer = setTimeout(processNextAutoBatch, 3000);
      return;
    }

    // Queue next batch
    state.autoQueueSubmitting = true;
    if (dom.batchLiveProgressTitle) {
      dom.batchLiveProgressTitle.textContent = `Queueing ${nextBatch.label} (${nextBatch.range})...`;
    }

    const success = await queueBatchByIndex(nextBatch.index);
    state.autoQueueSubmitting = false;

    if (success) {
      if (dom.batchLiveProgressTitle) {
        dom.batchLiveProgressTitle.textContent = `${nextBatch.label} Queued. Checking next batch...`;
      }
      if (state.autoQueueRetryTimer) clearTimeout(state.autoQueueRetryTimer);
      state.autoQueueRetryTimer = setTimeout(processNextAutoBatch, 1500);
    } else {
      togglePauseAutoBatch();
      showToast(`Batch ${nextBatch.index + 1} encountered an error. Auto-queue paused.`, 'error');
    }
  }

  function checkBatchCompletionStatus() {
    if (state.structuredBatches.length === 0) return;

    let allCompleted = true;
    for (const b of state.structuredBatches) {
      if (b.status === 'RUNNING' && b.jobIds && b.jobIds.length > 0) {
        const batchJobs = b.jobIds.map((jid) => state.jobs.get(jid)).filter(Boolean);
        if (batchJobs.length === b.jobIds.length) {
          const isDone = batchJobs.every((j) => j.status === 'COMPLETED' || j.status === 'FAILED');
          if (isDone) {
            b.status = 'COMPLETED';
          } else {
            allCompleted = false;
          }
        } else {
          allCompleted = false;
        }
      } else if (b.status !== 'COMPLETED') {
        allCompleted = false;
      }
    }

    updateBatchProgressUI();
    renderBatchItemsList();

    if (allCompleted && state.autoQueueActive) {
      state.autoQueueActive = false;
      if (dom.batchOrchestratorStatus) {
        dom.batchOrchestratorStatus.textContent = 'All Batches Finished!';
        dom.batchOrchestratorStatus.className = 'batch-assistant__status-pill active';
      }
      if (dom.btnBatchPause) dom.btnBatchPause.classList.add('hidden');
      if (dom.btnBatchCancel) dom.btnBatchCancel.classList.add('hidden');
      if (dom.btnBatchAutoAll) dom.btnBatchAutoAll.classList.remove('hidden');
      if (dom.btnBatchDownloadFirst) dom.btnBatchDownloadFirst.classList.remove('hidden');
      showToast('🎉 All batches and downloads have finished!', 'success');
    }
  }

  // Window helper bindings for dynamic elements
  window._queueBatchByIndex = function (index) {
    queueBatchByIndex(index);
  };

  window._toggleBatchPreview = function (index) {
    const el = document.getElementById(`batch-preview-${index}`);
    if (el) el.classList.toggle('hidden');
  };

  // =========================================================================
  // Metadata Fetch
  // =========================================================================

  async function fetchMetadata() {
    const url = dom.urlInput.value.trim();
    if (!url || !validateSingleUrl()) return;

    if (state.isFetchingMeta) return;
    state.isFetchingMeta = true;
    dom.btnFetchMeta.disabled = true;

    try {
      const resp = await fetchAPI(API.METADATA, {
        method: 'POST',
        body: JSON.stringify({ url }),
      });

      if (resp.success) {
        const d = resp.data;
        state.lastFetchedMeta = d;
        dom.metaTitle.textContent = d.title || 'Unknown Title';

        let detail = '';
        if (d.uploader) detail += d.uploader;
        if (d.duration) detail += ` · ${formatDuration(d.duration)}`;
        const isMix = Boolean(d.is_mix || (d.playlist_id && d.playlist_id.startsWith('RD')));
        if (!isMix && (d.url_type === 'playlist' || d.has_playlist)) {
          detail += ` · Playlist (${d.item_count || '?'} items)`;
          if (dom.playlistOptions) {
            dom.playlistOptions.classList.remove('hidden');
            if (dom.playlistOptionsTitle && d.title) {
              dom.playlistOptionsTitle.textContent = d.title;
            }
          }
        } else {
          if (isMix) detail += ' · YouTube Mix (Single Song)';
          if (dom.playlistOptions) {
            dom.playlistOptions.classList.add('hidden');
          }
        }
        dom.metaDetail.textContent = detail;

        dom.metaThumb.innerHTML = '';
        const thumbUrl = d.thumbnail || getYouTubeThumbnail(url);
        if (thumbUrl) {
          const img = document.createElement('img');
          img.src = thumbUrl;
          img.alt = d.title || 'Thumbnail';
          dom.metaThumb.appendChild(img);
        }

        dom.metaPreview.classList.remove('hidden');
      } else {
        showToast(resp.error?.message || 'Could not fetch metadata.', 'error');
      }
    } catch (err) {
      showToast('Network error fetching metadata.', 'error');
    } finally {
      state.isFetchingMeta = false;
      dom.btnFetchMeta.disabled = false;
    }
  }

  // =========================================================================
  // Single Download Submission
  // =========================================================================

  async function submitSingleDownload() {
    const url = dom.urlInput.value.trim();
    if (!url) {
      setFeedback(dom.urlFeedback, 'Please enter a URL.', 'error');
      dom.urlInput.focus();
      return;
    }

    if (!validateSingleUrl()) {
      dom.urlInput.focus();
      return;
    }

    if (state.isSubmitting) return;

    let quality = dom.qualitySelect.value;
    let formatType = state.formatType;

    if (formatType === 'audio') {
      quality = dom.audioFormatSelect.value;
    }

    const playlistMatch = url.match(/[?&]list=([a-zA-Z0-9_-]+)/i);
    const playlistId = playlistMatch ? playlistMatch[1] : null;
    const isMix = Boolean(playlistId && (playlistId.startsWith('RD') || playlistId === 'LL' || playlistId === 'WL' || playlistId === 'LM'));
    const hasPlaylist = Boolean(playlistId && !isMix) || (url.includes('/playlist?') && !isMix);
    const downloadType = hasPlaylist ? state.playlistMode : 'video';

    const eagerThumbnail = (state.lastFetchedMeta && state.lastFetchedMeta.thumbnail) || getYouTubeThumbnail(url);
    const eagerTitle = (state.lastFetchedMeta && state.lastFetchedMeta.title) || '';

    setSubmitting(dom.btnDownload, true);

    try {
      const resp = await fetchAPI(API.DOWNLOADS, {
        method: 'POST',
        body: JSON.stringify({
          url,
          quality,
          format_type: formatType,
          download_type: downloadType,
          title: eagerTitle,
          thumbnail: eagerThumbnail,
        }),
      });

      if (resp.success) {
        const d = resp.data;
        if (d.notice) {
          showToast(d.notice, 'info');
        }
        if (d.is_playlist) {
          showToast(`Playlist queued: ${d.total} videos`, 'success');
          if (d.jobs && Array.isArray(d.jobs)) {
            for (const j of d.jobs) {
              const jid = j.job_id || j.id;
              if (jid) {
                state.sessionJobIds.add(jid);
                state.jobs.set(jid, {
                  id: jid,
                  url: j.url,
                  title: j.title || '',
                  thumbnail: j.thumbnail || getYouTubeThumbnail(j.url),
                  status: j.status || 'QUEUED',
                  quality,
                  format_type: formatType,
                  created_at: new Date().toISOString(),
                });
              }
            }
          }
        } else {
          showToast('Download queued!', 'success');
          const jid = d.job_id || d.id;
          if (jid) {
            state.sessionJobIds.add(jid);
            state.jobs.set(jid, {
              id: jid,
              url: d.url || url,
              title: d.title || eagerTitle || '',
              thumbnail: d.thumbnail || eagerThumbnail || getYouTubeThumbnail(d.url || url),
              status: 'QUEUED',
              quality,
              format_type: formatType,
              created_at: new Date().toISOString(),
            });
          }
        }

        if (isHistoryStorageAllowed()) {
          saveStoredHistory(Array.from(state.jobs.values()));
        }

        renderCurrentJobs();
        updateActiveCount();

        dom.urlInput.value = '';
        dom.metaPreview.classList.add('hidden');
        if (dom.playlistOptions) dom.playlistOptions.classList.add('hidden');
        setFeedback(dom.urlFeedback, '', '');
        dom.urlInput.classList.remove('success', 'error');
        state.lastFetchedMeta = null;
        startPolling();
      } else {
        showToast(resp.error?.message || 'Failed to submit download.', 'error');
      }
    } catch (err) {
      showToast('Network error. Please try again.', 'error');
    } finally {
      setSubmitting(dom.btnDownload, false);
    }
  }

  // =========================================================================
  // Bulk Download Submission
  // =========================================================================

  async function submitBulkDownload() {
    const { valid } = validateBulkUrls();
    if (valid.length === 0) {
      setFeedback(dom.bulkFeedback, 'No valid URLs to submit.', 'error');
      dom.bulkInput.focus();
      return;
    }

    // Intercept when URL count exceeds the single batch limit (e.g. 142 URLs > 20 limit)
    if (valid.length > state.bulkBatchLimit) {
      if (dom.bulkBatchAssistant) {
        dom.bulkBatchAssistant.classList.remove('hidden');
        dom.bulkBatchAssistant.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      showToast(
        `${valid.length} URLs detected (limit is ${state.bulkBatchLimit} per batch). Starting structured auto-queue...`,
        'info'
      );
      startAutoBatchProcessing();
      return;
    }

    if (state.isSubmitting) return;

    const quality = dom.bulkQualitySelect.value;
    const formatType = state.bulkFormatType;

    setSubmitting(dom.btnBulkDownload, true);

    try {
      const resp = await fetchAPI(API.BATCHES, {
        method: 'POST',
        body: JSON.stringify({ urls: valid, quality, format_type: formatType }),
      });

      if (resp.success) {
        const d = resp.data;
        let msg = `Batch queued: ${d.total} videos`;
        if (d.duplicates_removed > 0) msg += ` (${d.duplicates_removed} duplicates removed)`;
        showToast(msg, 'success');

        if (d.jobs && Array.isArray(d.jobs)) {
          for (const j of d.jobs) {
            const jid = j.job_id || j.id;
            if (jid) {
              state.sessionJobIds.add(jid);
              state.jobs.set(jid, {
                id: jid,
                url: j.url,
                title: j.title || '',
                thumbnail: j.thumbnail || getYouTubeThumbnail(j.url),
                status: j.status || 'QUEUED',
                quality,
                format_type: formatType,
                created_at: new Date().toISOString(),
              });
            }
          }
        }

        if (isHistoryStorageAllowed()) {
          saveStoredHistory(Array.from(state.jobs.values()));
        }

        renderCurrentJobs();
        updateActiveCount();

        dom.bulkInput.value = '';
        dom.bulkSummary.classList.add('hidden');
        setFeedback(dom.bulkFeedback, '', '');
        startPolling();
      } else {
        showToast(resp.error?.message || 'Failed to submit batch.', 'error');
      }
    } catch (err) {
      showToast('Network error. Please try again.', 'error');
    } finally {
      setSubmitting(dom.btnBulkDownload, false);
    }
  }

  // =========================================================================
  // Browser Storage & History Permission Management (NO POPUPS)
  // =========================================================================

  function isHistoryStorageAllowed() {
    try {
      return localStorage.getItem(STORAGE_KEYS.PERMISSION) === 'true';
    } catch {
      return false;
    }
  }

  function setHistoryStorageAllowed(allowed) {
    try {
      localStorage.setItem(STORAGE_KEYS.PERMISSION, allowed ? 'true' : 'false');
      if (!allowed) {
        localStorage.removeItem(STORAGE_KEYS.HISTORY);
      }
    } catch (e) {
      console.warn('Storage permission error:', e);
    }
    updateStorageUI();
  }

  function updateStorageUI() {
    const allowed = isHistoryStorageAllowed();
    if (dom.toggleHistoryStorage) {
      dom.toggleHistoryStorage.checked = allowed;
    }
    if (dom.storageStatusBadge) {
      dom.storageStatusBadge.textContent = allowed ? 'Enabled' : 'Disabled';
      dom.storageStatusBadge.className = `storage-toggle-badge ${allowed ? 'enabled' : 'disabled'}`;
    }
    if (dom.emptyStateText && dom.emptyStateHint) {
      if (allowed) {
        dom.emptyStateText.textContent = 'No download history yet';
        dom.emptyStateHint.textContent = 'History storage is enabled. Videos you download will be saved in your browser storage.';
      } else {
        dom.emptyStateText.textContent = 'No active downloads';
        dom.emptyStateHint.textContent = 'History storage is disabled. Past video links are not stored. Start a download above to track it here during this session.';
      }
    }
  }

  function getStoredHistory() {
    if (!isHistoryStorageAllowed()) return [];
    try {
      const data = localStorage.getItem(STORAGE_KEYS.HISTORY);
      if (!data) return [];
      const parsed = JSON.parse(data);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function saveStoredHistory(jobsArray) {
    if (!isHistoryStorageAllowed()) return;
    try {
      const slice = jobsArray.slice(0, 100);
      localStorage.setItem(STORAGE_KEYS.HISTORY, JSON.stringify(slice));
    } catch (e) {
      console.warn('Failed to save history to storage:', e);
    }
  }

  function handleStorageToggle(e) {
    const allowed = e.target.checked;
    setHistoryStorageAllowed(allowed);

    if (allowed) {
      const currentJobs = Array.from(state.jobs.values()).sort(
        (a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)
      );
      saveStoredHistory(currentJobs);
      showToast('History storage enabled. Video links will be saved in your browser storage.', 'success');
      startPolling();
    } else {
      try {
        localStorage.removeItem(STORAGE_KEYS.HISTORY);
      } catch (err) {}

      const activeOnly = [];
      for (const [id, job] of state.jobs.entries()) {
        if (state.sessionJobIds.has(id) && (job.status === 'QUEUED' || job.status === 'RUNNING')) {
          activeOnly.push(job);
        } else {
          state.jobs.delete(id);
        }
      }
      renderJobs(activeOnly);
      updateActiveCount();
      showToast('History storage disabled. Stored video links cleared from browser storage.', 'info');
    }
  }

  function handleClearHistory() {
    try {
      localStorage.removeItem(STORAGE_KEYS.HISTORY);
    } catch (e) {}

    const activeOnly = [];
    for (const [id, job] of state.jobs.entries()) {
      if (state.sessionJobIds.has(id) && (job.status === 'QUEUED' || job.status === 'RUNNING')) {
        activeOnly.push(job);
      } else {
        state.jobs.delete(id);
      }
    }
    renderJobs(activeOnly);
    updateActiveCount();
    showToast('Download history cleared from browser storage.', 'info');
  }

  function removeJobFromHistory(jobId) {
    state.jobs.delete(jobId);
    state.sessionJobIds.delete(jobId);

    if (isHistoryStorageAllowed()) {
      const remaining = Array.from(state.jobs.values()).filter((j) => j.id !== jobId);
      saveStoredHistory(remaining);
    }

    const card = dom.jobsList.querySelector(`#job-${jobId}`);
    if (card) card.remove();

    renderCurrentJobs();
    updateActiveCount();
    showToast('Item removed from history.', 'info');
  }

  function renderCurrentJobs() {
    const allowed = isHistoryStorageAllowed();
    let jobsList = [];
    if (allowed) {
      jobsList = Array.from(state.jobs.values());
    } else {
      for (const id of state.sessionJobIds) {
        const j = state.jobs.get(id);
        if (j) jobsList.push(j);
      }
    }
    jobsList.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    renderJobs(jobsList);
  }

  // =========================================================================
  // Job Polling
  // =========================================================================

  function startPolling() {
    if (state.pollingTimer) {
      clearTimeout(state.pollingTimer);
      state.pollingTimer = null;
    }
    pollJobs();
  }

  async function pollJobs() {
    const allowed = isHistoryStorageAllowed();
    let idsToPoll = [];

    if (allowed) {
      const allIds = new Set([...state.jobs.keys(), ...state.sessionJobIds]);
      idsToPoll = Array.from(allIds);
    } else {
      idsToPoll = Array.from(state.sessionJobIds);
    }

    if (idsToPoll.length === 0) {
      state.pollingTimer = null;
      return;
    }

    try {
      const resp = await fetchAPI(`${API.JOBS}?ids=${encodeURIComponent(idsToPoll.join(','))}`);
      if (resp.success) {
        state.pollErrors = 0;
        const serverJobs = resp.data.jobs || [];

        for (const sJob of serverJobs) {
          // Preserve locally-stored thumbnail/title if the server doesn't return one yet
          const existing = state.jobs.get(sJob.id);
          if (existing) {
            if (!sJob.thumbnail && existing.thumbnail) sJob.thumbnail = existing.thumbnail;
            if (!sJob.title && existing.title) sJob.title = existing.title;
          }
          state.jobs.set(sJob.id, sJob);
        }

        if (allowed) {
          const allJobsList = Array.from(state.jobs.values()).sort(
            (a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)
          );
          saveStoredHistory(allJobsList);
        }

        renderCurrentJobs();
        updateActiveCount();

        checkBatchCompletionStatus();
        if (state.autoQueueActive && !state.autoQueuePaused) {
          processNextAutoBatch();
        }

        let hasActive = false;
        for (const id of idsToPoll) {
          const j = state.jobs.get(id);
          if (j && (j.status === 'QUEUED' || j.status === 'RUNNING')) {
            hasActive = true;
            break;
          }
        }

        if (hasActive || state.autoQueueActive) {
          state.pollingTimer = setTimeout(pollJobs, POLL_INTERVAL_ACTIVE);
        } else if (allowed && state.jobs.size > 0) {
          state.pollingTimer = setTimeout(pollJobs, POLL_INTERVAL_IDLE);
        } else {
          state.pollingTimer = null;
        }
      }
    } catch {
      state.pollErrors++;
      if (state.pollErrors < MAX_POLL_ERRORS) {
        state.pollingTimer = setTimeout(pollJobs, POLL_INTERVAL_IDLE);
      } else {
        state.pollingTimer = null;
      }
    }
  }

  function loadJobs() {
    updateStorageUI();

    if (isHistoryStorageAllowed()) {
      const stored = getStoredHistory();
      for (const job of stored) {
        state.jobs.set(job.id, job);
      }
      renderCurrentJobs();
      updateActiveCount();
      if (stored.length > 0) {
        startPolling();
      }
    } else {
      renderJobs([]);
      updateActiveCount();
    }
  }


  // =========================================================================
  // Job Rendering
  // =========================================================================

  function getDownloadFilename(job) {
    const title = job.title || 'video';
    let safe = title.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').trim();
    safe = safe.replace(/\s+/g, ' ').replace(/^\.+|\.+$/g, '');
    if (!safe) safe = 'download';

    let ext = 'mp4';
    if (job.filename && job.filename.includes('.')) {
      ext = job.filename.split('.').pop();
    } else if (job.format_type === 'audio' || (job.quality && job.quality.startsWith('audio_'))) {
      ext = (job.quality === 'audio_mp3') ? 'mp3' : 'm4a';
    }
    return `${safe}.${ext}`;
  }

  function renderJobs(jobs) {
    if (jobs.length === 0) {
      dom.emptyState.classList.remove('hidden');
      const cards = dom.jobsList.querySelectorAll('.job-card');
      cards.forEach((c) => c.remove());
      return;
    }

    dom.emptyState.classList.add('hidden');

    const jobIdsInResponse = new Set(jobs.map((j) => j.id));

    // Remove cards no longer in the response
    const existingCards = dom.jobsList.querySelectorAll('.job-card');
    existingCards.forEach((card) => {
      const cardJobId = card.id.replace('job-', '');
      if (!jobIdsInResponse.has(cardJobId)) {
        card.remove();
      }
    });

    // Update existing cards in-place (no flicker) or append newly created cards
    jobs.forEach((job, index) => {
      let card = dom.jobsList.querySelector(`#job-${job.id}`);
      if (card) {
        updateJobCard(card, job);
      } else {
        card = createJobCard(job);
        const currentCards = dom.jobsList.querySelectorAll('.job-card');
        if (index < currentCards.length) {
          dom.jobsList.insertBefore(card, currentCards[index]);
        } else {
          dom.jobsList.appendChild(card);
        }
      }
    });
  }

  function updateJobCard(card, job) {
    const status = job.status;
    const title = job.title || truncateUrl(job.url);

    // 0. Thumbnail (update src if it changed)
    const thumbImg = card.querySelector('.job-card__thumb');
    const thumbPlaceholder = card.querySelector('.job-card__thumb-placeholder');
    const thumbUrl = job.thumbnail || getYouTubeThumbnail(job.url);
    if (thumbUrl && thumbImg) {
      if (thumbImg.src !== thumbUrl) thumbImg.src = thumbUrl;
      if (thumbPlaceholder) thumbPlaceholder.style.display = 'none';
      thumbImg.style.display = 'block';
    } else if (!thumbUrl && thumbImg) {
      thumbImg.style.display = 'none';
      if (thumbPlaceholder) thumbPlaceholder.style.display = '';
    }

    // 1. Status dot
    const dot = card.querySelector('.job-card__dot');
    if (dot && !dot.classList.contains(status)) {
      dot.className = `job-card__dot ${status}`;
    }

    // 2. Title
    const titleEl = card.querySelector('.job-card__title');
    if (titleEl && titleEl.textContent !== title) {
      titleEl.textContent = title;
      titleEl.title = job.url;
    }

    // 3. Status text badge
    const statusEl = card.querySelector('.job-card__status');
    if (statusEl) {
      if (!statusEl.classList.contains(status)) {
        statusEl.className = `job-card__status ${status}`;
      }
      if (statusEl.textContent !== status) {
        statusEl.textContent = status;
      }
    }

    // 4. Progress bar (smooth transition without jumping)
    let progressBar = card.querySelector('.progress-bar');
    if (status === 'RUNNING') {
      if (!progressBar) {
        progressBar = document.createElement('div');
        progressBar.className = 'progress-bar';
        const fill = document.createElement('div');
        fill.className = 'progress-bar__fill';
        progressBar.appendChild(fill);
        const header = card.querySelector('.job-card__header');
        if (header) {
          header.insertAdjacentElement('afterend', progressBar);
        } else {
          const body = card.querySelector('.job-card__body') || card;
          body.appendChild(progressBar);
        }
      }
      const fill = progressBar.querySelector('.progress-bar__fill');
      if (fill) {
        if (job.progress_percent != null) {
          fill.classList.remove('indeterminate');
          fill.style.width = `${Math.min(job.progress_percent, 100)}%`;
        } else {
          fill.classList.add('indeterminate');
          fill.style.width = '';
        }
      }
    } else if (progressBar) {
      progressBar.remove();
    }

    // 5. Stats
    let statsEl = card.querySelector('.job-card__stats');
    let statsParts = [];
    if (status === 'RUNNING') {
      if (job.progress_percent != null) statsParts.push(`${job.progress_percent.toFixed(1)}%`);
      if (job.speed) statsParts.push(`${formatBytes(job.speed)}/s`);
      if (job.eta != null) statsParts.push(`ETA: ${formatETA(job.eta)}`);
      if (job.downloaded_bytes && job.total_bytes) {
        statsParts.push(`${formatBytes(job.downloaded_bytes)} / ${formatBytes(job.total_bytes)}`);
      }
    } else if (status === 'COMPLETED' && job.file_size) {
      statsParts.push(`📁 ${formatBytes(job.file_size)}`);
    }

    if (statsParts.length > 0) {
      const statsHtml = statsParts.map((p) => `<span class="job-card__stat">${escapeHtml(p)}</span>`).join('');
      if (!statsEl) {
        statsEl = document.createElement('div');
        statsEl.className = 'job-card__stats';
        const body = card.querySelector('.job-card__body') || card;
        const ref = body.querySelector('.progress-bar') || body.querySelector('.job-card__header');
        if (ref) ref.insertAdjacentElement('afterend', statsEl);
        else body.appendChild(statsEl);
      }
      if (statsEl.innerHTML !== statsHtml) {
        statsEl.innerHTML = statsHtml;
      }
    } else if (statsEl) {
      statsEl.remove();
    }

    // 6. Error
    let errorEl = card.querySelector('.job-card__error');
    if (status === 'FAILED' && job.error_message) {
      if (!errorEl) {
        errorEl = document.createElement('div');
        errorEl.className = 'job-card__error';
        const body = card.querySelector('.job-card__body') || card;
        body.appendChild(errorEl);
      }
      if (errorEl.textContent !== job.error_message) {
        errorEl.textContent = job.error_message;
      }
    } else if (errorEl) {
      errorEl.remove();
    }

    // 7. Actions (Download link with explicit filename + delete button)
    let actionsEl = card.querySelector('.job-card__actions');
    const canRetry = (job.retry_count || 0) < (job.max_retries || 3);
    const deleteBtnHtml = `<button type="button" class="job-card__btn-delete" title="Remove from history" onclick="window._removeHistoryItem('${job.id}')" aria-label="Remove from history">🗑️ Remove</button>`;

    let actionHtml = '';
    if (status === 'COMPLETED') {
      const filename = getDownloadFilename(job);
      const downloadUrl = `${API.JOBS}/${job.id}/file/${encodeURIComponent(filename)}`;
      actionHtml = `<a href="${downloadUrl}" class="btn btn--download btn--small" download="${escapeHtml(filename)}">📥 Download File</a> ${deleteBtnHtml}`;
    } else if (status === 'FAILED') {
      actionHtml = canRetry
        ? `<button type="button" class="btn btn--retry btn--small" onclick="window._retryJob('${job.id}')">🔄 Retry</button> ${deleteBtnHtml}`
        : `<span class="job-card__stat">Max retries reached</span> ${deleteBtnHtml}`;
    } else {
      actionHtml = deleteBtnHtml;
    }

    if (!actionsEl) {
      actionsEl = document.createElement('div');
      actionsEl.className = 'job-card__actions';
      const body = card.querySelector('.job-card__body') || card;
      body.appendChild(actionsEl);
    }
    if (actionsEl.innerHTML !== actionHtml) {
      actionsEl.innerHTML = actionHtml;
    }
  }

  function createJobCard(job) {
    const card = document.createElement('div');
    card.className = 'job-card';
    card.id = `job-${job.id}`;

    const title = escapeHtml(job.title || truncateUrl(job.url));
    const status = job.status;
    const thumbUrl = job.thumbnail || getYouTubeThumbnail(job.url);

    let progressHtml = '';
    if (status === 'RUNNING') {
      const percent = job.progress_percent;
      if (percent != null) {
        progressHtml = `
          <div class="progress-bar">
            <div class="progress-bar__fill" style="width: ${Math.min(percent, 100)}%"></div>
          </div>`;
      } else {
        progressHtml = `
          <div class="progress-bar">
            <div class="progress-bar__fill indeterminate"></div>
          </div>`;
      }
    }

    let statsHtml = '';
    if (status === 'RUNNING') {
      const parts = [];
      if (job.progress_percent != null) parts.push(`${job.progress_percent.toFixed(1)}%`);
      if (job.speed) parts.push(`${formatBytes(job.speed)}/s`);
      if (job.eta != null) parts.push(`ETA: ${formatETA(job.eta)}`);
      if (job.downloaded_bytes && job.total_bytes) {
        parts.push(`${formatBytes(job.downloaded_bytes)} / ${formatBytes(job.total_bytes)}`);
      }
      if (parts.length > 0) {
        statsHtml = `<div class="job-card__stats">${parts.map((p) => `<span class="job-card__stat">${escapeHtml(p)}</span>`).join('')}</div>`;
      }
    }

    if (status === 'COMPLETED' && job.file_size) {
      statsHtml = `<div class="job-card__stats"><span class="job-card__stat">📁 ${formatBytes(job.file_size)}</span></div>`;
    }

    let actionsHtml = '';
    const canRetry = (job.retry_count || 0) < (job.max_retries || 3);
    const deleteBtnHtml = `<button type="button" class="job-card__btn-delete" title="Remove from history" onclick="window._removeHistoryItem('${job.id}')" aria-label="Remove from history">🗑️ Remove</button>`;

    if (status === 'COMPLETED') {
      const filename = getDownloadFilename(job);
      const downloadUrl = `${API.JOBS}/${job.id}/file/${encodeURIComponent(filename)}`;
      actionsHtml = `<div class="job-card__actions">
        <a href="${downloadUrl}" class="btn btn--download btn--small" download="${escapeHtml(filename)}">📥 Download File</a>
        ${deleteBtnHtml}
      </div>`;
    } else if (status === 'FAILED') {
      actionsHtml = `<div class="job-card__actions">
        ${canRetry ? `<button type="button" class="btn btn--retry btn--small" onclick="window._retryJob('${job.id}')">🔄 Retry</button>` : '<span class="job-card__stat">Max retries reached</span>'}
        ${deleteBtnHtml}
      </div>`;
    } else {
      actionsHtml = `<div class="job-card__actions">
        ${deleteBtnHtml}
      </div>`;
    }

    let errorHtml = '';
    if (status === 'FAILED' && job.error_message) {
      errorHtml = `<div class="job-card__error">${escapeHtml(job.error_message)}</div>`;
    }

    const videoLinkHtml = job.url ? `<a href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer" class="job-card__link" title="Open YouTube video (opens in new tab)">🔗 Video Link</a>` : '';

    const formatBadge = job.format_type === 'audio' ? 'AUDIO' : 'VIDEO';
    const thumbHtml = `
      <div class="job-card__thumb-container">
        <img class="job-card__thumb" src="${escapeHtml(thumbUrl || '')}" alt="thumbnail"
             style="${thumbUrl ? '' : 'display:none'}" loading="lazy">
        <span class="job-card__thumb-placeholder" style="${thumbUrl ? 'display:none' : ''}">🎬</span>
        <span class="job-card__thumb-badge">${formatBadge}</span>
      </div>`;

    card.innerHTML = `
      <div class="job-card__layout">
        ${thumbHtml}
        <div class="job-card__body">
          <div class="job-card__header">
            <span class="job-card__dot ${status}"></span>
            <span class="job-card__title" title="${escapeHtml(job.url || '')}">${title}</span>
            ${videoLinkHtml}
            <span class="job-card__status ${status}">${status}</span>
          </div>
          ${progressHtml}
          ${statsHtml}
          ${errorHtml}
          ${actionsHtml}
        </div>
      </div>
    `;

    return card;
  }

  function updateActiveCount() {
    let active = 0;
    for (const [, job] of state.jobs) {
      if (job.status === 'QUEUED' || job.status === 'RUNNING') active++;
    }
    dom.activeCount.textContent = active;
  }

  // =========================================================================
  // Retry & History Removal
  // =========================================================================

  window._retryJob = async function (jobId) {
    try {
      const resp = await fetchAPI(`${API.JOBS}/${jobId}/retry`, { method: 'POST' });
      if (resp.success) {
        state.sessionJobIds.add(jobId);
        const existing = state.jobs.get(jobId);
        if (existing) {
          existing.status = 'QUEUED';
          existing.error_message = null;
          existing.progress_percent = null;
          renderJobCard(existing);
        }
        showToast('Job requeued for retry.', 'success');
        startPolling();
      } else {
        showToast(resp.error?.message || 'Retry failed.', 'error');
      }
    } catch {
      showToast('Network error during retry.', 'error');
    }
  };

  window._removeHistoryItem = function (jobId) {
    removeJobFromHistory(jobId);
  };

  // =========================================================================
  // API Helpers
  // =========================================================================

  async function fetchAPI(url, options = {}) {
    const defaults = {
      headers: { 'Content-Type': 'application/json' },
    };
    const config = { ...defaults, ...options };
    if (!options.method || options.method === 'GET') {
      delete config.headers['Content-Type'];
    }

    const response = await fetch(url, config);

    // Handle non-JSON responses
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return { success: true };
    }

    return response.json();
  }

  // =========================================================================
  // UI Helpers
  // =========================================================================

  function setFeedback(el, message, type) {
    el.textContent = message;
    el.className = 'form-feedback' + (type ? ` ${type}` : '');
  }

  function setSubmitting(btn, submitting) {
    state.isSubmitting = submitting;
    btn.disabled = submitting;
    const text = btn.querySelector('.btn__text');
    const spinner = btn.querySelector('.btn__spinner');
    if (submitting) {
      if (text) text.textContent = 'Submitting...';
      if (spinner) spinner.classList.remove('hidden');
    } else {
      if (text) text.textContent = btn.id === 'btn-bulk-download' ? 'Download All' : 'Download';
      if (spinner) spinner.classList.add('hidden');
    }
  }

  // =========================================================================
  // Toast Notifications
  // =========================================================================

  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    dom.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('removing');
      toast.addEventListener('animationend', () => toast.remove());
    }, TOAST_DURATION);
  }

  // =========================================================================
  // Formatting Utilities
  // =========================================================================

  function formatBytes(bytes) {
    if (bytes == null || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function formatETA(seconds) {
    if (seconds == null) return '—';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${(seconds / 3600).toFixed(1)}h`;
  }

  function truncateUrl(url) {
    if (!url) return 'Unknown';
    if (url.length > 60) return url.substring(0, 57) + '...';
    return url;
  }

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function debounce(fn, delay) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  // =========================================================================
  // Start
  // =========================================================================

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
