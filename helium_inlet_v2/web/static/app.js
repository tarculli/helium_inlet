// CHART 1: PRESSURE (LOG SCALE)
const ctxP = document.getElementById('pressureChart').getContext('2d');
const pressureChart = new Chart(ctxP, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { label: 'Chamber (115)', borderColor: '#2563eb', data: [], tension: 0.1, borderWidth: 2, pointRadius: 0 },
            { label: 'Trap (116)', borderColor: '#d97706', data: [], tension: 0.1, borderWidth: 2, pointRadius: 0 },
            { label: 'LoVac (119)', borderColor: '#059669', data: [], tension: 0.1, borderWidth: 2, pointRadius: 0 }
        ]
    },
    options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        scales: {
            x: { ticks: { color: '#475569', font: { size: 9 } }, grid: { display: false } },
            y: { type: 'logarithmic', min: 1e-8, max: 1e3, grid: { color: '#e2e8f0' } }
        },
        plugins: { legend: { labels: { color: '#0f172a', font: { size: 10, weight: '600' } } } }
    }
});

// CHART 2: TEMPERATURE
const ctxT = document.getElementById('tempChart').getContext('2d');
const tempChart = new Chart(ctxT, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { label: 'Eng B HR (101)', borderColor: '#d97706', data: [], tension: 0.2, borderWidth: 1.5, pointRadius: 0 },
            { label: 'Eng B PV (102)', borderColor: '#2563eb', data: [], tension: 0.2, borderWidth: 1.5, pointRadius: 0 },
            { label: 'Eng A PV (103)', borderColor: '#059669', data: [], tension: 0.2, borderWidth: 1.5, pointRadius: 0 },
            { label: 'Eng A HR (104)', borderColor: '#db2777', data: [], tension: 0.2, borderWidth: 1.5, pointRadius: 0 }
        ]
    },
    options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        scales: {
            x: { ticks: { color: '#475569', font: { size: 9 } }, grid: { display: false } },
            y: { ticks: { color: '#475569', font: { size: 9 } }, grid: { color: '#e2e8f0' } }
        },
        plugins: { legend: { labels: { color: '#0f172a', font: { size: 10, weight: '600' } } } }
    }
});

// LOG RENDERER
let lastLogCount = 0;
function renderLogs(logs) {
    if (!logs || logs.length === lastLogCount) return;
    lastLogCount = logs.length;
    const box = document.getElementById("logBox");
    box.innerHTML = "";
    logs.forEach(log => {
        const entry = document.createElement("div");
        entry.className = "log-entry";
        let tagClass = log.level === "SUCCESS" ? "tag-success" : (log.level === "WARN" ? "tag-warn" : "tag-info");
        entry.innerHTML = `<span class="log-time">${log.time}</span><span class="log-tag ${tagClass}">${log.level}</span><span class="log-msg">${log.msg}</span>`;
        box.appendChild(entry);
    });
    box.scrollTop = box.scrollHeight;
}

// WEBSOCKET TELEMETRY CONNECTION
const ws = new WebSocket(`ws://${location.host}/ws/telemetry`);
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);

    // Update Panel Cards
    document.getElementById("status").innerText = data.status;
    document.getElementById("device").innerText = data.device;
    document.getElementById("timestamp").innerText = data.timestamp;

    document.getElementById("ch101").innerText = data.ch101;
    document.getElementById("ch102").innerText = data.ch102;
    document.getElementById("ch103").innerText = data.ch103;
    document.getElementById("ch104").innerText = data.ch104;
    document.getElementById("ch115_p").innerText = data.ch115_p;
    document.getElementById("ch115_v").innerText = data.ch115_v;
    document.getElementById("ch116_p").innerText = data.ch116_p;
    document.getElementById("ch116_v").innerText = data.ch116_v;
    document.getElementById("ch119_p").innerText = data.ch119_p;
    document.getElementById("ch119_v").innerText = data.ch119_v;
    document.getElementById("ch113").innerText = data.ch113;
    document.getElementById("ch112").innerText = data.ch112;

    // Bind Live Readouts Directly Into SVG Plumbing Diagram Nodes
    document.getElementById("svg_temp_a").innerText = data.ch103;
    document.getElementById("svg_temp_b").innerText = data.ch102;
    document.getElementById("svg_p115").innerText = "115: " + data.ch115_p;

    // Chart Data Streaming (60 Point Rolling Window)
    const now = new Date().toLocaleTimeString();
    if (pressureChart.data.labels.length > 60) {
        pressureChart.data.labels.shift();
        pressureChart.data.datasets.forEach(d => d.data.shift());
        tempChart.data.labels.shift();
        tempChart.data.datasets.forEach(d => d.data.shift());
    }

    pressureChart.data.labels.push(now);
    pressureChart.data.datasets[0].data.push(data.ch115_p_val);
    pressureChart.data.datasets[1].data.push(data.ch116_p_val);
    pressureChart.data.datasets[2].data.push(data.ch119_p_val);
    pressureChart.update();

    tempChart.data.labels.push(now);
    tempChart.data.datasets[0].data.push(data.ch101_val);
    tempChart.data.datasets[1].data.push(data.ch102_val);
    tempChart.data.datasets[2].data.push(data.ch103_val);
    tempChart.data.datasets[3].data.push(data.ch104_val);
    tempChart.update();

    renderLogs(data.logs);
};