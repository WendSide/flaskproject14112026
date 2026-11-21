(function() {
    const modal = document.getElementById('zoomModal');
    const fullImg = document.getElementById('zoomFullImg');
    const zoomImg = document.getElementById('zoomImg');

    if (!zoomImg || !modal || !fullImg) return;

    zoomImg.onclick = function() {
        fullImg.src = this.src;
        modal.classList.add('active');
    };

    modal.onclick = function() {
        modal.classList.remove('active');
    };
})();