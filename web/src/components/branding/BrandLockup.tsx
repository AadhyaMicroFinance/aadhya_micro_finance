import Image from "next/image";

type Variant = "sidebar" | "header" | "login" | "document";

const variants: Record<Variant, { image: string; width: number; height: number; title: string; attribution: string }> = {
  sidebar: { image: "h-8 w-10", width: 40, height: 32, title: "text-sm font-bold", attribution: "text-[10px]" },
  header: { image: "h-7 w-9", width: 36, height: 28, title: "text-[11px] font-bold uppercase sm:text-sm", attribution: "text-[10px] sm:text-[11px]" },
  login: { image: "h-14 w-20", width: 92, height: 62, title: "text-xl font-bold uppercase sm:text-2xl", attribution: "text-sm" },
  document: { image: "h-12 w-16", width: 64, height: 52, title: "text-base font-bold", attribution: "text-xs" },
};

export default function BrandLockup({ variant = "header", className = "" }: { variant?: Variant; className?: string }) {
  const style = variants[variant];
  if (variant === "login") {
    return <div className={`select-none text-center ${className}`}>
      <div className="mb-4 inline-flex rounded-xl bg-white p-2 shadow-lg"><Image src="/amf-logo.png" alt="Aadhya Micro Finance logo" width={style.width} height={style.height} className={`${style.image} object-contain`} draggable={false} priority /></div>
      <h1 className={`${style.title} leading-tight tracking-wide text-white`}>Aadhya Micro Finance<span className="block text-sm font-semibold tracking-[0.18em] text-brand-200 sm:text-base">Private Limited</span></h1>
      <p className={`mt-2 text-surface-400 ${style.attribution}`}>Powered by Vayu Integration Services</p>
    </div>;
  }
  return <div className={`flex min-w-0 select-none items-center gap-3 ${className}`}>
    <Image src="/amf-logo.png" alt="Aadhya Micro Finance logo" width={style.width} height={style.height} className={`${style.image} rounded bg-white object-contain`} draggable={false} priority={variant === "sidebar"} />
    <div className="min-w-0"><span className={`block truncate tracking-tight text-surface-900 ${style.title}`}>Aadhya Micro Finance</span><span className={`block truncate text-surface-400 ${style.attribution}`}>Powered by Vayu Integration Services</span></div>
  </div>;
}
