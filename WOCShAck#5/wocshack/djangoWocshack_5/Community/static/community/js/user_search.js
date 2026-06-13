const input = document.getElementById("search-input");
const form = document.getElementById("search-form");
const results = document.getElementById("search-results");

const url = form.dataset.url;

let timeout = null;

window.onload = () => {
  input.focus();
};

input.addEventListener("input", function () {

    clearTimeout(timeout);

    timeout = setTimeout(() => {

        const query = input.value;

        fetch(`${url}?q=${encodeURIComponent(query)}`, {
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        })
        .then(response => response.text())
        .then(html => {
            results.innerHTML = html;
        });

    }, 300);

});