// Sparkline renderer for any element with data-spark='[...]'
// Lets pages render charts client-side without server-coupling.
(function () {
  function render(el) {
    const data = JSON.parse(el.dataset.spark || '[]');
    const variant = el.dataset.variant || 'bullish';
    if (data.length < 2) return;
    const w = el.clientWidth || 100;
    const h = el.clientHeight || 40;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const step = w / (data.length - 1);
    let path = '';
    let area = '';
    data.forEach((v, i) => {
      const x = (i * step).toFixed(2);
      const y = (h - ((v - min) / range) * h).toFixed(2);
      path += (i === 0 ? 'M' : 'L') + x + ',' + y + ' ';
      area += (i === 0 ? 'M' + x + ',' + h + ' L' : 'L') + x + ',' + y + ' ';
    });
    area += 'L' + w + ',' + h + ' Z';
    el.innerHTML =
      `<svg class="spark ${variant}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:100%;">` +
      `<path class="area-${variant}" d="${area}"/>` +
      `<path d="${path}"/>` +
      `</svg>`;
  }
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-spark]').forEach(render);
  });
})();
