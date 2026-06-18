type Props = {
  value: number;
  label: string;
};

export default function StatCard({ value, label }: Props) {
  return (
    <div className="flex flex-col rounded-xl h-fit w-[20%] bg-zinc-600/50 items-center justify-center px-6 py-6 border-zinc-400 border border-opacity-50">
      <div className="text-xl lg:text-4xl font-bold w-full h-fit text-center text-nowrap">
        {value}
      </div>
      <div className="mt-4 text-center w-full">{label}</div>
    </div>
  );
}
