// ローカル環境の自動検出 — ヘッダー色・タイトルで本番と区別
(function() {
  var h = location.hostname;
  if (h === 'localhost' || h === '127.0.0.1' || h === '0.0.0.0') {
    document.title = '[DEV] ' + document.title;
    document.addEventListener('DOMContentLoaded', function() {
      var header = document.querySelector('.header');
      if (header) {
        header.classList.add('dev');
        var badge = document.createElement('span');
        badge.className = 'dev-badge';
        badge.textContent = 'DEV';
        var h1 = header.querySelector('h1');
        if (h1) h1.appendChild(badge);
      }
    });
  }
})();
