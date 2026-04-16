// Main JavaScript for TechStore

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Back to top button
    const backToTopButton = document.createElement('button');
    backToTopButton.className = 'back-to-top';
    backToTopButton.innerHTML = '<i class="fas fa-chevron-up"></i>';
    backToTopButton.style.display = 'none';
    document.body.appendChild(backToTopButton);
    
    window.addEventListener('scroll', function() {
        if (window.pageYOffset > 300) {
            backToTopButton.style.display = 'flex';
        } else {
            backToTopButton.style.display = 'none';
        }
    });
    
    backToTopButton.addEventListener('click', function() {
        window.scrollTo({top: 0, behavior: 'smooth'});
    });
    
    // Quantity increment/decrement
    document.querySelectorAll('.quantity-btn').forEach(button => {
        button.addEventListener('click', function() {
            const input = this.parentNode.querySelector('.quantity-input');
            const currentValue = parseInt(input.value);
            
            if (this.classList.contains('decrease') && currentValue > 1) {
                input.value = currentValue - 1;
            } else if (this.classList.contains('increase')) {
                input.value = currentValue + 1;
            }
            
            // Trigger change event
            input.dispatchEvent(new Event('change'));
        });
    });
    
    // Image zoom
    document.querySelectorAll('.product-zoom').forEach(image => {
        image.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.1)';
            this.style.transition = 'transform 0.3s ease';
        });
        
        image.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    });
    
    // Add to cart animation
    document.querySelectorAll('.add-to-cart-btn').forEach(button => {
        button.addEventListener('click', function(e) {
            const btn = this;
            const originalText = btn.innerHTML;
            
            // Add loading animation
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Adding...';
            btn.disabled = true;
            
            // Simulate API call
            setTimeout(() => {
                btn.innerHTML = '<i class="fas fa-check"></i> Added!';
                btn.classList.add('btn-success');
                
                // Update cart count
                updateCartCount(1);
                
                // Reset button after 2 seconds
                setTimeout(() => {
                    btn.innerHTML = originalText;
                    btn.classList.remove('btn-success');
                    btn.disabled = false;
                }, 2000);
            }, 1000);
        });
    });
    
    // Form validation
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;
            
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    field.classList.add('is-invalid');
                    isValid = false;
                } else {
                    field.classList.remove('is-invalid');
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                alert('Please fill in all required fields.');
            }
        });
    });
    
    // Price range filter
    const priceRangeMin = document.getElementById('priceRangeMin');
    const priceRangeMax = document.getElementById('priceRangeMax');
    const priceMinValue = document.getElementById('priceMinValue');
    const priceMaxValue = document.getElementById('priceMaxValue');
    
    if (priceRangeMin && priceRangeMax) {
        priceRangeMin.addEventListener('input', function() {
            priceMinValue.textContent = '$' + this.value;
        });
        
        priceRangeMax.addEventListener('input', function() {
            priceMaxValue.textContent = '$' + this.value;
        });
    }
    
    // Product image gallery
    document.querySelectorAll('.product-thumbnail').forEach(thumb => {
        thumb.addEventListener('click', function() {
            const mainImage = document.getElementById('mainProductImage');
            mainImage.src = this.src;
            
            // Update active thumbnail
            document.querySelectorAll('.product-thumbnail').forEach(t => {
                t.classList.remove('active');
            });
            this.classList.add('active');
        });
    });
    
    // Wishlist toggle
    document.querySelectorAll('.wishlist-toggle').forEach(button => {
        button.addEventListener('click', function() {
            const icon = this.querySelector('i');
            
            if (icon.classList.contains('far')) {
                icon.classList.remove('far');
                icon.classList.add('fas', 'text-danger');
                this.classList.add('active');
            } else {
                icon.classList.remove('fas', 'text-danger');
                icon.classList.add('far');
                this.classList.remove('active');
            }
        });
    });
    
    // Mobile menu toggle
    const mobileMenuToggle = document.getElementById('mobileMenuToggle');
    const mobileMenu = document.getElementById('mobileMenu');
    
    if (mobileMenuToggle) {
        mobileMenuToggle.addEventListener('click', function() {
            mobileMenu.classList.toggle('show');
        });
    }
    
    // Lazy loading images
    const lazyImages = document.querySelectorAll('img[data-src]');
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
                observer.unobserve(img);
            }
        });
    });
    
    lazyImages.forEach(img => imageObserver.observe(img));
});

// Utility functions
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function updateCartCount(increment = 0) {
    const cartCountElement = document.querySelector('.cart-count');
    if (cartCountElement) {
        const currentCount = parseInt(cartCountElement.textContent) || 0;
        cartCountElement.textContent = currentCount + increment;
        
        // Add animation
        cartCountElement.classList.add('pulse');
        setTimeout(() => {
            cartCountElement.classList.remove('pulse');
        }, 300);
    }
}

function showToast(message, type = 'success') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999;';
        document.body.appendChild(container);
    }
    
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} alert-dismissible fade show`;
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.getElementById('toast-container').appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

// Cart functions
function addToCart(productId, quantity = 1) {
    fetch(`/cart/add/${productId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({quantity: quantity})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateCartCount(quantity);
            showToast('Product added to cart!', 'success');
        } else {
            showToast(data.message || 'Failed to add product', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('An error occurred', 'danger');
    });
}

function removeFromCart(itemId) {
    if (confirm('Are you sure you want to remove this item?')) {
        fetch(`/cart/remove/${itemId}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                showToast('Failed to remove item', 'danger');
            }
        });
    }
}

// Wishlist functions
function toggleWishlist(productId) {
    fetch(`/wishlist/toggle/${productId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
        }
    });
}

// Search functionality
function performSearch(query) {
    if (query.trim().length > 0) {
        window.location.href = `/search/?q=${encodeURIComponent(query)}`;
    }
}

// Initialize on page load
window.addEventListener('load', function() {
    // Fade in content
    document.body.classList.add('loaded');
    
    // Initialize any animations
    AOS.init({
        duration: 1000,
        once: true,
        offset: 100
    });
});