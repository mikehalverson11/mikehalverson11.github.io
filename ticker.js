// ticker.js
document.addEventListener('DOMContentLoaded', function() {
    fetch('ticker.txt')
        .then(response => response.text())
        .then(data => {
            const ticker = document.getElementById('ticker');
            // Split by | and repeat content for seamless loop
            const items = data.split('|').map(item => item.trim());
            const tickerHTML = items.join(' • ') + ' • ' + items.join(' • ');
            ticker.textContent = tickerHTML;
        });
});
