// ticker.js
document.addEventListener('DOMContentLoaded', function() {
    fetch('ticker.txt')
        .then(response => response.text())
        .then(data => {
            const ticker = document.getElementById('ticker');
            // Split by | and create the content
            const items = data.split('|').map(item => item.trim());
            const content = items.join(' • ');
            
            // Duplicate the content multiple times for seamless looping
            ticker.textContent = content + ' • ' + content + ' • ' + content;
        });
});
