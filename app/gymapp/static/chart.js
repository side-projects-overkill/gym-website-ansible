/* Minimal dependency-free line chart for metric trends. */
async function fetchMetricHistory(metricKey) {
    const res = await fetch(`/tracker/history/${metricKey}`);
    return res.json();
}

function drawTrendChart(canvas, points, emptyEl) {
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.clientWidth;
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (!points || points.length === 0) {
        if (emptyEl) emptyEl.style.display = 'block';
        return;
    }
    if (emptyEl) emptyEl.style.display = 'none';

    const pad = 36;
    const values = points.map(p => p.value);
    const minV = Math.min(...values), maxV = Math.max(...values);
    const range = (maxV - minV) || 1;
    const plotRight = w - 20;

    const xAt = (i) => pad + (i / Math.max(points.length - 1, 1)) * (plotRight - pad);
    const yAt = (v) => h - pad - ((v - minV) / range) * (h - pad - 20);

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad, h - pad);
    ctx.lineTo(plotRight, h - pad);
    ctx.moveTo(pad, 10);
    ctx.lineTo(pad, h - pad);
    ctx.stroke();

    ctx.fillStyle = '#9497ab';
    ctx.font = '11px sans-serif';
    ctx.fillText(maxV.toFixed(1), 2, 16);
    ctx.fillText(minV.toFixed(1), 2, h - pad);

    // Soft gradient fill under the line for a "glowing" app-like look.
    if (points.length > 1) {
        const fillGradient = ctx.createLinearGradient(0, 10, 0, h - pad);
        fillGradient.addColorStop(0, 'rgba(91, 124, 255, 0.35)');
        fillGradient.addColorStop(1, 'rgba(91, 124, 255, 0)');
        ctx.fillStyle = fillGradient;
        ctx.beginPath();
        ctx.moveTo(xAt(0), h - pad);
        points.forEach((p, i) => ctx.lineTo(xAt(i), yAt(p.value)));
        ctx.lineTo(xAt(points.length - 1), h - pad);
        ctx.closePath();
        ctx.fill();
    }

    const lineGradient = ctx.createLinearGradient(pad, 0, plotRight, 0);
    lineGradient.addColorStop(0, '#5b7cff');
    lineGradient.addColorStop(1, '#8b5cf6');
    ctx.strokeStyle = lineGradient;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    points.forEach((p, i) => {
        const x = xAt(i), y = yAt(p.value);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();

    points.forEach((p, i) => {
        const x = xAt(i), y = yAt(p.value);
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#8b5cf6';
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = '#0a0b12';
        ctx.stroke();
    });

    ctx.fillStyle = '#9497ab';
    ctx.fillText(points[0].date, pad, h - pad + 14);
    if (points.length > 1) {
        const lastX = plotRight;
        ctx.fillText(points[points.length - 1].date, lastX - 60, h - pad + 14);
    }
}

async function loadAndDrawChart(metricKey, canvas, emptyEl) {
    const data = await fetchMetricHistory(metricKey);
    drawTrendChart(canvas, data.points || [], emptyEl);
}

/* Minimal axis-less line, for compact "bento" cards (e.g. the dashboard's
   weight-goal widget) where drawTrendChart's labels/padding would be too
   cramped at a small canvas height. */
function drawSparkline(canvas, points) {
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.clientWidth;
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    if (!points || points.length < 2) return;

    const pad = 4;
    const values = points.map(p => p.value);
    const minV = Math.min(...values), maxV = Math.max(...values);
    const range = (maxV - minV) || 1;
    const xAt = (i) => pad + (i / (points.length - 1)) * (w - pad * 2);
    const yAt = (v) => h - pad - ((v - minV) / range) * (h - pad * 2);

    const fillGradient = ctx.createLinearGradient(0, 0, 0, h);
    fillGradient.addColorStop(0, 'rgba(91, 124, 255, 0.3)');
    fillGradient.addColorStop(1, 'rgba(91, 124, 255, 0)');
    ctx.fillStyle = fillGradient;
    ctx.beginPath();
    ctx.moveTo(xAt(0), h - pad);
    points.forEach((p, i) => ctx.lineTo(xAt(i), yAt(p.value)));
    ctx.lineTo(xAt(points.length - 1), h - pad);
    ctx.closePath();
    ctx.fill();

    const lineGradient = ctx.createLinearGradient(0, 0, w, 0);
    lineGradient.addColorStop(0, '#5b7cff');
    lineGradient.addColorStop(1, '#8b5cf6');
    ctx.strokeStyle = lineGradient;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    points.forEach((p, i) => {
        const x = xAt(i), y = yAt(p.value);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
}

async function loadAndDrawSparkline(metricKey, canvas) {
    const data = await fetchMetricHistory(metricKey);
    drawSparkline(canvas, data.points || []);
}
