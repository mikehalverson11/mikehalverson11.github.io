// load-book-reviews.js
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('book-modal');
    let reviewsData = null;
    let booksByYear = {};

    // Fetch the reviews data
    fetch('books.json')
        .then(response => response.json())
        .then(data => {
            reviewsData = data;
            organizeBooksByYear(data);
            createYearDropdown();
            generateBookList('all'); // Show all books initially
        });

    // Organize books by year
    function organizeBooksByYear(data) {
        const sortedBooks = Object.entries(data).sort((a, b) => {
            const dateA = new Date(a[1].day_read);
            const dateB = new Date(b[1].day_read);
            return dateB - dateA;
        });

        sortedBooks.forEach(([id, book]) => {
            const year = new Date(book.day_read).getFullYear();
            if (!booksByYear[year]) {
                booksByYear[year] = [];
            }
            booksByYear[year].push({ id, ...book });
        });
    }

    // Create the year dropdown
    function createYearDropdown() {
        const mainContainer = document.querySelector('.main');
        
        const filterDiv = document.createElement('div');
        filterDiv.className = 'year-filter';
        filterDiv.innerHTML = `
            <label for="year-select">Filter by year: </label>
            <select id="year-select">
                <option value="all">All Years</option>
            </select>
        `;
        
        // Add years to dropdown (most recent first)
        const years = Object.keys(booksByYear).sort((a, b) => b - a);
        const select = filterDiv.querySelector('#year-select');
        years.forEach(year => {
            const option = document.createElement('option');
            option.value = year;
            option.textContent = year;
            select.appendChild(option);
        });

        // Insert at the top of main
        mainContainer.insertBefore(filterDiv, mainContainer.firstChild);

        // Add event listener for dropdown changes
        select.addEventListener('change', function() {
            generateBookList(this.value);
        });
    }

    // Generate the book list based on selected year
    function generateBookList(selectedYear) {
        const mainContainer = document.querySelector('.main');
        
        // Remove old book list (keep the filter)
        const oldContent = mainContainer.querySelectorAll('h1, h2, ul');
        oldContent.forEach(el => el.remove());

        // Add the Books header
        const header = document.createElement('h1');
        header.style.backgroundColor = 'powderblue';
        header.style.marginBottom = '0';
        header.textContent = 'Books';
        mainContainer.appendChild(header);

        // Filter years to display
        const yearsToShow = selectedYear === 'all' 
            ? Object.keys(booksByYear).sort((a, b) => b - a)
            : [selectedYear];

        // Generate HTML for each year
        yearsToShow.forEach(year => {
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
