document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("search-form")
    const logo = document.getElementById("logo-text")
    const arrow = document.getElementById("arrow-icon")

    if (form && logo && arrow) {
        form.addEventListener("submit", (e) => {
            e.preventDefault()

            form.classList.remove("border-4", "lg:h-[100px]", "h-[70px]", "py-3", "pr-3", "pl-10", "lg:w-[50%]", "w-[95%]")
            form.classList.add("border-2", "lg:h-[60px]", "h-[40px]", "py-2", "pr-2", "pl-7", "lg:w-[40%]", "w-[60%]", "absolute", "top-1/4", "left-1/2", "transform", "-translate-x-1/2")

            logo.classList.remove("text-9xl", "mb-28")
            logo.classList.add("text-7xl", "self-start", "ml-10", "mt-10")

            arrow.classList.remove("lg:w-[48px]", "lg:h-[48px]", "w-[30px]", "h-[30px]")
            arrow.classList.add("lg:w-[32px]", "lg:h-[32px]", "w-[24px]", "h-[24px]")

            document.body.style.justifyContent = "flex-start"
        });
    }
});

