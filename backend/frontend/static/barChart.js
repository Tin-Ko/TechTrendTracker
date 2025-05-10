const loadChart = async (jobTitle) => {
    console.log("loading")
    const response = await fetch(`/skills?job_title=${encodeURIComponent(jobTitle)}`);
    const data = await response.json();
    console.log("data: ", data);

    const ctx = document.getElementById("tech-skills-chart").getContext('2d');
    // ctx.canvas.style.backgroundColor = 'rgba(82, 82, 92, 0.5)';

    if (window.chartInstance) {
        window.chartInstance.destroy();
    }

    window.chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.Skills.map(s => s.Name),
            datasets: [{
                label: "Skill",
                data: data.Skills.map(s => s.Count),
                backgroundColor: "#7ab2ff",
                borderRadius: 10,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            // aspectRatio: 2,
            layout: {
                padding: 40,
            },
            plugins: {
                title: {
                    display: true,
                    text: 'Skills in Demand',
                    font: {
                        size: 40,
                        weight: 'bold',
                        family: 'Segoe UI',
                    },
                    color: 'white',
                    position: 'top',
                    align: 'start',
                    padding: {
                        left: 30,
                        bottom: 30,
                    }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const skillData = data.Skills[context.dataIndex];
                            return [
                                `Count: ${skillData.Count}`,
                                `Percentage: ${skillData.Percentage.toFixed(2)}%`
                            ]
                        }
                    },
                },
                legend: {
                    display: false,
                    labels: {
                        color: 'rgba(255, 255, 255, 1)',
                        font: {
                            size: 12,
                        }
                    }
                }
            },
            parsing: {
                yAxisKey: 'count'
            },
            scales: {
                x: {
                    ticks: {
                        color: 'rgba(255, 255, 255, 1)',
                        font: {
                            size: 14,
                        }
                    },
                    grid: {
                        display: false,
                    },
                },
                y: {
                    ticks: {
                        color: 'rgba(255, 255, 255, 1)',
                        font: {
                            size: 14,
                        }
                    },
                    beginAtZero: true,
                    border: {
                        display: false,
                    }
                }
            }
        }
    });
    if(window.chartInstance){
        window.chartInstance.resize();
    }
}

const jobTitle = document.getElementById("chart-container").dataset.jobTitle;
console.log("got job title: ", jobTitle);
if (jobTitle) {
    loadChart(jobTitle);
}
