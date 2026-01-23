// load-life.js
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('life-modal');
    let lifeData = null;

    // Fetch the life updates data
    fetch('life.json')
        .then(response => response.json())
        .then(data => {
            lifeData = data;
            generateLifeGrid(data);
        });

    // Generate the life updates grid
    function generateLifeGrid(data) {
        const lifeGrid = document.getElementById('life-grid');
        
        // Sort life updates by date (most recent first)
        const sortedUpdates = Object.entries(data).sort((a, b) => {
            const dateA = new Date(a[1].date_published);
            const dateB = new Date(b[1].date_published);
            return dateB - dateA;
        });

        // Generate life update cards
        sortedUpdates.forEach(([id, update]) => {
            const updateCard = document.createElement('div');
            updateCard.className = 'blog-card'; // Reusing blog-card styles
            
            // Use custom image if provided, otherwise default to old computer
            const imageSrc = update.image || 'Images/oldcomputer.jpg';
            
            updateCard.innerHTML = `
                <a href="#${id}" class="blog-link">
                    <img src="${imageSrc}" alt="${update.title}">
                    <div class="blog-info">
                        <h3>${update.title}</h3>
                        <p class="blog-date">${update.date_published}</p>
                    </div>
                </a>
            `;
            
            lifeGrid.appendChild(updateCard);
        });
    }

    // Listen for hash changes (clicking life update links)
    window.addEventListener('hashchange', function() {
        const hash = window.location.hash.substring(1);
        
        if (hash && lifeData && lifeData[hash]) {
            showLifeUpdate(hash);
        } else if (!hash) {
            hideModal();
        }
    });

    // Check if page loads with a hash already
    if (window.location.hash) {
        const hash = window.location.hash.substring(1);
        const checkData = setInterval(() => {
            if (lifeData && lifeData[hash]) {
                showLifeUpdate(hash);
                clearInterval(checkData);
            }
        }, 100);
    }

    function showLifeUpdate(updateId) {
        const update = lifeData[updateId];
        const modalContent = modal.querySelector('.modal-content');
        
        // Handle line breaks - split into paragraphs
        const paragraphs = update.content.split('\n')
            .filter(p => p.trim())
            .map(p => `<p>${p}</p>`)
            .join('');
        
        // Set the content
        modalContent.innerHTML = `
            <a href="#" class="close">&times;</a>
            <h2>${update.title}</h2>
            <p><em>Published: ${update.date_published}</em></p>
            ${paragraphs}
        `;
        
        // Show the modal
        modal.classList.add('show');
    }

    function hideModal() {
        modal.classList.remove('show');
    }
});