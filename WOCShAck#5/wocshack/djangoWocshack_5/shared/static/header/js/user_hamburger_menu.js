document.addEventListener('DOMContentLoaded', () => {
    const header = document.querySelector('header');
    const user_offScreenMenu = document.querySelector('.user-off-screen-menu');
    const user_button = document.querySelector('.user_button');
    const todo_button_right = document.querySelector('.todo_button_right');

    function adjustMenuPosition() {
        const headerHeight = header ? header.offsetHeight : 0;
        user_offScreenMenu.style.top = `${headerHeight}px`;
    }

    // Initial positioning
    adjustMenuPosition();

    // Recalculate on resize
    window.addEventListener('resize', adjustMenuPosition);

    // Toggle menu
    const toggleMenu = (event) => {
        event.stopPropagation();
        user_offScreenMenu.classList.toggle('active');
    };

    if (user_button) {
        user_button.addEventListener('click', toggleMenu);
    }

    // Close menu when clicking outside
    document.addEventListener('click', (event) => {
        const isClickInsideMenu = user_offScreenMenu.contains(event.target);
        const isClickOnUserButton = user_button && user_button.contains(event.target);
        const isClickOnTodoButton = todo_button_right && todo_button_right.contains(event.target);

        if (!isClickInsideMenu && !isClickOnUserButton && !isClickOnTodoButton) {
            user_offScreenMenu.classList.remove('active');
        }
    });
});
