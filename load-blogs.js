// load-blogs.js
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('blog-modal');
    let blogsData = null;

    // Fetch the blogs data
    fetch('blogs.json')
        .then(response => response.json())
        .then(data => {
            blogsData = data;
            generateBlogGrid(data);
        });

    // Generate the blog grid
    function generateBlogGrid(data) {
        const blogGrid = document.getElementById('blog-grid');
        
        // Sort blogs by date (most recent first)
        const sortedBlogs = Object.entries(data).sort((a, b) => {
            const dateA = new Date(a[1].date_published);
            const dateB = new Date(b[1].date_published);
            return dateB - dateA;
        });

        // Generate blog cards
        sortedBlogs.forEach(([id, blog]) => {
            const blogCard = document.createElement('div');
            blogCard.className = 'blog-card';
            
            // Use custom image if provided, otherwise default to old computer
            const imageSrc = blog.image || 'Images/oldcomputer.jpg';
            
            blogCard.innerHTML = `
                <a href="#${id}" class="blog-link">
                    <img src="${imageSrc}" alt="${blog.title}">
                    <div class="blog-info">
                        <h3>${blog.title}</h3>
                        <p class="blog-date">${blog.date_published}</p>
                    </div>
                </a>
            `;
            
            blogGrid.appendChild(blogCard);
        });
    }

    // Listen for hash changes (clicking blog links)
    window.addEventListener('hashchange', function() {
        const hash = window.location.hash.substring(1);
        
        if (hash && blogsData && blogsData[hash]) {
            showBlog(hash);
        } else if (!hash) {
            hideModal();
        }
    });

    // Check if page loads with a hash already
    if (window.location.hash) {
        const hash = window.location.hash.substring(1);
        const checkData = setInterval(() => {
            if (blogsData && blogsData[hash]) {
                showBlog(hash);
                clearInterval(checkData);
            }
        }, 100);
    }

    function showBlog(blogId) {
        const blog = blogsData[blogId];
        const modalContent = modal.querySelector('.modal-content');
        
        // Handle line breaks - split into paragraphs
        const paragraphs = blog.content.split('\n')
            .filter(p => p.trim())
            .map(p => `<p>${p}</p>`)
            .join('');
        
        // Set the content
        modalContent.innerHTML = `
            <a href="#" class="close">&times;</a>
            <h2>${blog.title}</h2>
            <p><em>Published: ${blog.date_published}</em></p>
            ${paragraphs}
        `;
        
        // Show the modal
        modal.classList.add('show');
    }

    function hideModal() {
        modal.classList.remove('show');
    }
});