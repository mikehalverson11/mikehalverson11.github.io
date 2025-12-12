// load-book-reviews.js
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('book-modal') || createModal();
    let reviewsData = null;

    // Fetch the reviews data
    fetch('books.json')
        .then(response => response.json())
        .then(data => {
            reviewsData = data;
            generateBookList(data);
        });

    // Create modal if it doesn't exist
    function createModal() {
        const modal = document.createElement('div');
        modal.id = 'book-modal';
        modal.className = 'modal';
        modal.innerHTML = '<div class="modal-content"></div>';
        document.body.appendChild(modal);
        return modal;
    }

    // Generate the book list from JSON data
    function generateBookList(data) {
        const bookListContainer = document.querySelector('.main ul');
        if (!bookListContainer) return;

        // Clear existing list
        bookListContainer.innerHTML = '';

        // Sort books by date (most recent first)
        const sortedBooks = Object.entries(data).sort((a, b) => {
            const dateA = new Date(a[1].day_read);
            const dateB = new Date(b[1].day_read);
            return dateB - dateA;
        });

        // Group books by year
        const booksByYear = {};
        sortedBooks.forEach(([id, book]) => {
            const year = new Date(book.day_read).getFullYear();
            if (!booksByYear[year]) {
                booksByYear[year] = [];
            }
            booksByYear[year].push({ id, ...book });
        });

        // Generate HTML for each year
        const mainContainer = document.querySelector('.main');
        mainContainer.innerHTML = '<h1 style="background-color:powderblue;margin-bottom:0;font-family:Courier">Books</h1>';

        Object.keys(booksByYear).sort((a, b) => b - a).forEach(year => {
            const yearHeader = document.createElement('h2');
            yearHeader.style.marginTop = '0';
            yearHeader.style.marginBottom = '0';
            yearHeader.textContent = year;
            mainContainer.appendChild(yearHeader);

            const ul = document.createElement('ul');
            booksByYear[year].forEach(book => {
                const li = document.createElement('li');
                const link = document.createElement('a');
                link.href = `#${book.id}`;
                link.className = 'review-link';
                link.textContent = `${book.title} - ${book.author}`;
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

    function showReview(bookId) {
        const book = reviewsData[bookId];
        const modalContent = modal.querySelector('.modal-content');
        
        // Handle \n line breaks - split into paragraphs
        const paragraphs = book.review.split('\n')
            .filter(p => p.trim()) // Remove empty strings
            .map(p => `<p>${p}</p>`)
            .join('');
        
        // Set the content
        modalContent.innerHTML = `
            <a href="#" class="close">&times;</a>
            <h2>${book.title}</h2>
            <h3>by ${book.author}</h3>
            <p><em>Read on: ${book.day_read} | Rating: ${book.stars}/5 stars</em></p>
            ${paragraphs}
        `;
        
        // Show the modal
        modal.classList.add('show');
    }

    function hideModal() {
        modal.classList.remove('show');
    }
});
