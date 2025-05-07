document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("search-form")
    const section = document.getElementById("search-section")

    if (form && section) {
        form.addEventListener("submit", () => {
            section.classList.remove("search-centered");
            section.classList.add("search-top")
            document.body.style.justifyContent = "flex-start"
        });
    }
});
