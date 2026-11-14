// ===== МОБИЛЬНОЕ МЕНЮ =====
const hamburger = document.querySelector('.hamburger');
const navMenu = document.querySelector('.nav-menu');

if (hamburger) {
    hamburger.addEventListener('click', () => {
        navMenu.classList.toggle('active');
        hamburger.classList.toggle('active');
    });
}

// ===== ЗАКРЫТИЕ FLASH СООБЩЕНИЙ =====
document.addEventListener('DOMContentLoaded', () => {
    const closeButtons = document.querySelectorAll('.close-flash');
    
    closeButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const message = btn.closest('.flash-message');
            message.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                message.remove();
            }, 300);
        });
    });
    
    // Автоматическое скрытие flash сообщений через 5 секунд
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(msg => {
        setTimeout(() => {
            msg.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                msg.remove();
            }, 300);
        }, 5000);
    });
});

// ===== АНИМАЦИЯ ПРИ СКРОЛЛЕ =====
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Наблюдаем за карточками
document.addEventListener('DOMContentLoaded', () => {
    const cards = document.querySelectorAll('.car-card, .catalog-card, .part-card, .feature-card');
    
    cards.forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'all 0.6s ease';
        observer.observe(card);
    });
});

// ===== ПЛАВНЫЙ СКРОЛЛ =====
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// ===== ЭФФЕКТ PARALLAX ДЛЯ HERO =====
window.addEventListener('scroll', () => {
    const hero = document.querySelector('.hero');
    if (hero) {
        const scrolled = window.pageYOffset;
        hero.style.transform = `translateY(${scrolled * 0.5}px)`;
    }
});

// ===== ДОБАВЛЕНИЕ В ИЗБРАННОЕ ЧЕРЕЗ AJAX =====
function addToFavorite(partId) {
    fetch(`/add_favorite/${partId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Добавлено в избранное!', 'success');
        } else if (data.login_required) {
            window.location.href = '/login';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Ошибка при добавлении', 'error');
    });
}

// ===== УВЕДОМЛЕНИЯ =====
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `flash-message flash-${type}`;
    notification.innerHTML = `
        ${message}
        <span class="close-flash">&times;</span>
    `;
    
    let container = document.querySelector('.flash-messages');
    if (!container) {
        container = document.createElement('div');
        container.className = 'flash-messages';
        document.body.appendChild(container);
    }
    
    container.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// ===== ПОИСК =====
function searchParts(query) {
    fetch(`/api/search?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            // Обработка результатов поиска
            console.log(data);
        })
        .catch(error => console.error('Search error:', error));
}

// ===== АНИМАЦИЯ НЕОНА ПРИ КЛИКЕ =====
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('neon-text') || e.target.classList.contains('neon-text-red')) {
        e.target.style.animation = 'none';
        setTimeout(() => {
            e.target.style.animation = 'flicker 2s infinite alternate';
        }, 100);
    }
});