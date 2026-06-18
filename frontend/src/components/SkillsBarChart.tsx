import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Title,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";

import type { Skill } from "../types";

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

type Props = {
  skills: Skill[];
};

export default function SkillsBarChart({ skills }: Props) {
  if (!skills || skills.length === 0) {
    return (
      <div className="text-white/70 text-center py-16">
        No skills to show for this query yet.
      </div>
    );
  }

  return (
    <Bar
      data={{
        labels: skills.map((s) => s.Name),
        datasets: [
          {
            label: "Skill",
            data: skills.map((s) => s.Count),
            backgroundColor: "#7ab2ff",
            borderRadius: 10,
          },
        ],
      }}
      options={{
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: 40 },
        plugins: {
          title: {
            display: true,
            text: "Skills in Demand",
            font: { size: 40, weight: "bold", family: "Segoe UI" },
            color: "white",
            position: "top",
            align: "start",
            padding: { top: 0, bottom: 30 },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const s = skills[ctx.dataIndex];
                return [`Count: ${s.Count}`, `Percentage: ${s.Percentage.toFixed(2)}%`];
              },
            },
          },
          legend: { display: false },
        },
        scales: {
          x: {
            ticks: { color: "rgba(255, 255, 255, 1)", font: { size: 14 } },
            grid: { display: false },
          },
          y: {
            ticks: { color: "rgba(255, 255, 255, 1)", font: { size: 14 } },
            beginAtZero: true,
            border: { display: false },
          },
        },
      }}
    />
  );
}
