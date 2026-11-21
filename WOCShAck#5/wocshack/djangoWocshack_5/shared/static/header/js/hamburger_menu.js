window.addEventListener('load', adjustMenuPosition);
window.addEventListener('resize', adjustMenuPosition);

function adjustMenuPosition() {
    const header = document.querySelector('header');
    const offScreenMenu = document.querySelector('.off-screen-menu');
    const headerHeight = header.offsetHeight;
    offScreenMenu.style.top = `${headerHeight}px`;
}

const todo_button = document.querySelector(".Todo_button");
const menu_toggle = document.querySelector(".menu-toggle");
const offScreenMenu = document.querySelector(".off-screen-menu");

const toggleOffScreenMenu = (event) => {
    event.stopPropagation();
    offScreenMenu.classList.toggle("active");
};

todo_button.addEventListener("click", toggleOffScreenMenu);
if (menu_toggle) {
    menu_toggle.addEventListener("click", toggleOffScreenMenu);
}

// Close the menu when clicking outside of it
document.addEventListener("click", (event) => {
    const isClickInsideMenu = offScreenMenu.contains(event.target);
    const isClickOnButton = todo_button.contains(event.target);
    const isClickOnToggle = menu_toggle && menu_toggle.contains(event.target);

    if (!isClickInsideMenu && !isClickOnButton && !isClickOnToggle) {
        offScreenMenu.classList.remove("active");
    }
});
