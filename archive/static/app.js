// --- Config Management ---
async function saveConfig() {
    const config = {
        NOTION_API_KEY: document.getElementById('notion-api-key').value,
        NOTION_DATABASE_ID: document.getElementById('notion-db-id').value,
        XHS_BOARD_URL: document.getElementById('input-url').value,
        XHS_COOKIES: document.getElementById('input-cookies').value
    };

    await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    });
}

async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        const config = await res.json();

        if (config.NOTION_API_KEY) {
            document.getElementById('notion-api-key').value = config.NOTION_API_KEY;
            updateStatus('badge-notion', 'Saved Locally', 'waiting');
        }
        if (config.NOTION_DATABASE_ID) {
            document.getElementById('notion-db-id').value = config.NOTION_DATABASE_ID;
        }
        if (config.XHS_BOARD_URL) {
            document.getElementById('input-url').value = config.XHS_BOARD_URL;
            updateStatus('badge-source', 'Link Loaded', 'waiting');
        }
        if (config.XHS_COOKIES) {
            document.getElementById('input-cookies').value = JSON.stringify(config.XHS_COOKIES);
        }
    } catch (e) { console.error(e); }
}

function updateStatus(elementId, text, type) {
    const badge = document.getElementById(elementId);
    badge.textContent = text;
    // reset classes
    badge.className = 'status-badge';
    // add type
    if (type === 'connected' || type === 'valid') badge.classList.add('connected');
    else badge.classList.add('waiting'); // default gray
}

// --- Interaction Logic ---

// Toggle Settings
document.querySelectorAll('.toggle-settings').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const targetId = e.target.getAttribute('data-target');
        const panel = document.getElementById(targetId);

        if (panel.classList.contains('hidden')) {
            panel.classList.remove('hidden');
            e.target.textContent = 'Hide Settings';
        } else {
            panel.classList.add('hidden');
            e.target.textContent = 'Open Connection Settings';
        }
    });
});

// Verify Notion
document.getElementById('btn-verify-notion').addEventListener('click', async () => {
    const btn = document.getElementById('btn-verify-notion');
    btn.textContent = 'Testing...';
    btn.disabled = true;

    await saveConfig(); // Save first

    try {
        const res = await fetch('/api/verify/notion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: document.getElementById('notion-api-key').value,
                db_id: document.getElementById('notion-db-id').value
            })
        });
        const data = await res.json();

        if (data.status === 'ok') {
            updateStatus('badge-notion', 'Connected', 'connected');
            // Auto hide settings on success
            document.getElementById('settings-notion').classList.add('hidden');
            document.querySelector('.toggle-settings').textContent = 'Open Connection Settings';
        } else {
            alert('Connection Failed: ' + data.message);
            updateStatus('badge-notion', 'Check Settings', 'waiting');
        }
    } catch (e) {
        alert('Could not reach the server.');
    } finally {
        btn.textContent = 'Test Connection';
        btn.disabled = false;
    }
});

// Validate Cookies (Source)
document.getElementById('btn-validate-cookies').addEventListener('click', async () => {
    const btn = document.getElementById('btn-validate-cookies');
    btn.textContent = 'Checking...';
    btn.disabled = true;

    await saveConfig();

    try {
        const res = await fetch('/api/verify/xhs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                cookies: document.getElementById('input-cookies').value
            })
        });
        const data = await res.json();

        if (data.status === 'ok') {
            updateStatus('badge-source', 'Link Valid', 'valid');
            alert('Your cookies look good!');
        } else {
            alert('Something is wrong with the cookies: ' + data.message);
        }
    } finally {
        btn.textContent = 'Check Cookies';
        btn.disabled = false;
    }
});

// Start Sync
document.getElementById('btn-start-sync').addEventListener('click', async () => {
    const btn = document.getElementById('btn-start-sync');
    if (btn.disabled) return;

    await saveConfig();

    const incremental = document.getElementById('check-incremental').checked;
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-fill');
    const statusText = document.getElementById('status-text');
    const consoleLog = document.getElementById('console-log');

    // Reset UI
    progressContainer.classList.remove('hidden');
    btn.textContent = 'Saving...';
    btn.disabled = true;
    updateStatus('badge-sync', 'Saving...', 'valid');
    progressBar.style.width = '5%';
    consoleLog.innerHTML = ''; // Request clear

    try {
        const eventSource = new EventSource(`/api/sync?incremental=${incremental}`);

        eventSource.onmessage = (e) => {
            const data = JSON.parse(e.data);

            if (data.type === 'log') {
                const line = document.createElement('div');
                line.textContent = `> ${data.message}`;
                consoleLog.appendChild(line);
                consoleLog.scrollTop = consoleLog.scrollHeight;

                statusText.textContent = data.message;

                // Progress heuristics
                if (data.message.includes('Fetching')) progressBar.style.width = '20%';
                if (data.message.includes('Found')) progressBar.style.width = '40%';
                if (data.message.includes('Syncing:')) progressBar.style.width = '60%';
                if (data.message.includes('Success')) progressBar.style.width = '100%';

            } else if (data.type === 'done') {
                eventSource.close();
                finishSync(true);
            } else if (data.type === 'error') {
                eventSource.close();
                finishSync(false);
            }
        };

        eventSource.onerror = () => {
            eventSource.close();
            finishSync(false);
        };

    } catch (e) {
        finishSync(false);
    }
});

function finishSync(success) {
    const btn = document.getElementById('btn-start-sync');
    btn.disabled = false;
    btn.textContent = 'Start Saving';

    if (success) {
        updateStatus('badge-sync', 'Saved Successfully', 'valid');
        document.getElementById('status-text').textContent = 'All done! Notes are in Notion.';
    } else {
        updateStatus('badge-sync', 'Save Failed', 'waiting');
        document.getElementById('status-text').textContent = 'We ran into a problem.';
    }
}

// Init
window.addEventListener('DOMContentLoaded', loadConfig);
