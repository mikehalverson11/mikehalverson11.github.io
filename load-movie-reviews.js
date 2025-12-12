// load-movie-reviews.js
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('book-modal');
    let reviewsData = null;

    // Fetch the reviews data
    fetch('movies.json')
        .then(response => response.json())
        .then(data => {
            reviewsData = data;
            generateMovieList(data);
        });

    // Generate the movie list from JSON data
    function generateMovieList(data) {
        const mainContainer = document.querySelector('.main');
        if (!mainContainer) return;

        // Sort movie by date (most recent first)
        const sortedMovies = Object.entries(data).sort((a, b) => {
            const dateA = new Date(a[1].day_read);
            const dateB = new Date(b[1].day_read);
            return dateB - dateA;
        });

        // Group movies by year
        const moviesByYear = {};
        sortedMovies.forEach(([id, movie]) => {
            const year = new Date(movie.day_watched).getFullYear();
            if (!moviesByYear[year]) {
                moviesByYear[year] = [];
            }
            moviesByYear[year].push({ id, ...movie });
        });

        // Generate HTML for each year
        mainContainer.innerHTML = '<h1 style="background-color:powderblue;margin-bottom:0;">Movies</h1>';

        Object.keys(moviesByYear).sort((a, b) => b - a).forEach(year => {
            const yearHeader = document.createElement('h2');
            yearHeader.style.marginTop = '0';
            yearHeader.style.marginBottom = '0';
            yearHeader.textContent = year;
            mainContainer.appendChild(yearHeader);

            const ul = document.createElement('ul');
            moviesByYear[year].forEach(movie => {
                const li = document.createElement('li');
                const link = document.createElement('a');
                link.href = `#${movie.id}`;
                link.className = 'review-link';
                link.textContent = `${movie.title} - ${movie.author}`;
                li.appendChild(link);
                ul.appendChild(li);
            });
            mainContainer.appendChild(ul);
        });
    }

    // Listen for hash changes (clicking review links)
    window.addEventListener('hashchange', function() {
        const hash = window.location.hash.substring(1);
        
        if (hash && reviewsData && reviewsData[hash]) {
            showReview(hash);
        } else if (!hash) {
            hideModal();
        }
    });

    // Check if page loads with a hash already
    if (window.location.hash) {
        const hash = window.location.hash.substring(1);
        const checkData = setInterval(() => {
            if (reviewsData && reviewsData[hash]) {
                showReview(hash);
                clearInterval(checkData);
            }
        }, 100);
    }

    function showReview(movieId) {
        const movie = reviewsData[movieId];
        const modalContent = modal.querySelector('.modal-content');
        
        // Handle \n line breaks - split into paragraphs
        const paragraphs = movie.review.split('\n')
            .filter(p => p.trim()) // Remove empty strings
            .map(p => `<p>${p}</p>`)
            .join('');
        
        // Set the content
        modalContent.innerHTML = `
            <a href="#" class="close">&times;</a>
            <h2>${movie.title}</h2>
            <h3>by ${movie.director}</h3>
            <p><em>Watched on: ${movie.day_watched} | Rating: ${movie.stars}/5 stars</em></p>
            ${paragraphs}
        `;
        
        // Show the modal
        modal.classList.add('show');
    }

    function hideModal() {
        modal.classList.remove('show');
    }
});
