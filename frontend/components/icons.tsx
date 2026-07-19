import type { SVGProps } from "react";

export type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function IconBase({ size = 20, children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      {children}
    </svg>
  );
}

const stroke = {
  stroke: "currentColor",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  strokeWidth: 1.8,
};

export function ArrowRightIcon(props: IconProps) {
  return <IconBase {...props}><path d="M5 12h14m-5-5 5 5-5 5" {...stroke} /></IconBase>;
}
export function ArrowLeftIcon(props: IconProps) {
  return <IconBase {...props}><path d="m19 12-14 0m5 5-5-5 5-5" {...stroke} /></IconBase>;
}
export function DashboardIcon(props: IconProps) {
  return <IconBase {...props}><rect x="3" y="3" width="7" height="7" rx="2" {...stroke}/><rect x="14" y="3" width="7" height="7" rx="2" {...stroke}/><rect x="3" y="14" width="7" height="7" rx="2" {...stroke}/><rect x="14" y="14" width="7" height="7" rx="2" {...stroke}/></IconBase>;
}
export function ExamIcon(props: IconProps) {
  return <IconBase {...props}><path d="M7 3h10a2 2 0 0 1 2 2v16l-3-2-4 2-4-2-3 2V5a2 2 0 0 1 2-2Z" {...stroke}/><path d="M9 8h6M9 12h6" {...stroke}/></IconBase>;
}
export function PlusIcon(props: IconProps) { return <IconBase {...props}><path d="M12 5v14M5 12h14" {...stroke}/></IconBase>; }
export function ChartIcon(props: IconProps) { return <IconBase {...props}><path d="M4 20V10m6 10V4m6 16v-7m4 7H2" {...stroke}/></IconBase>; }
export function LogoutIcon(props: IconProps) { return <IconBase {...props}><path d="M10 17l5-5-5-5m5 5H3m10-8h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-5" {...stroke}/></IconBase>; }
export function MenuIcon(props: IconProps) { return <IconBase {...props}><path d="M4 7h16M4 12h16M4 17h16" {...stroke}/></IconBase>; }
export function CloseIcon(props: IconProps) { return <IconBase {...props}><path d="m6 6 12 12M18 6 6 18" {...stroke}/></IconBase>; }
export function CheckIcon(props: IconProps) { return <IconBase {...props}><path d="m5 12 4 4L19 6" {...stroke}/></IconBase>; }
export function UploadIcon(props: IconProps) { return <IconBase {...props}><path d="M12 16V4m0 0L7 9m5-5 5 5M5 14v5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5" {...stroke}/></IconBase>; }
export function FileIcon(props: IconProps) { return <IconBase {...props}><path d="M6 2h8l4 4v16H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z" {...stroke}/><path d="M14 2v5h4M8 12h6M8 16h6" {...stroke}/></IconBase>; }
export function TrashIcon(props: IconProps) { return <IconBase {...props}><path d="M4 7h16m-10 4v6m4-6v6M9 4h6l1 3H8l1-3Zm-3 3 1 14h10l1-14" {...stroke}/></IconBase>; }
export function SearchIcon(props: IconProps) { return <IconBase {...props}><circle cx="11" cy="11" r="7" {...stroke}/><path d="m20 20-4-4" {...stroke}/></IconBase>; }
export function CalendarIcon(props: IconProps) { return <IconBase {...props}><rect x="3" y="5" width="18" height="16" rx="2" {...stroke}/><path d="M16 3v4M8 3v4M3 10h18" {...stroke}/></IconBase>; }
export function UsersIcon(props: IconProps) { return <IconBase {...props}><path d="M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m7-10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.87m-2-11.99a4 4 0 0 1 0 7.75" {...stroke}/></IconBase>; }
export function AlertIcon(props: IconProps) { return <IconBase {...props}><path d="M10.3 3.6 2.2 18a2 2 0 0 0 1.75 3h16.1a2 2 0 0 0 1.75-3L13.7 3.6a2 2 0 0 0-3.4 0Z" {...stroke}/><path d="M12 9v4m0 4h.01" {...stroke}/></IconBase>; }
export function InfoIcon(props: IconProps) { return <IconBase {...props}><circle cx="12" cy="12" r="9" {...stroke}/><path d="M12 11v6m0-10h.01" {...stroke}/></IconBase>; }
export function RefreshIcon(props: IconProps) { return <IconBase {...props}><path d="M20 11a8 8 0 1 0-2.34 5.66M20 4v7h-7" {...stroke}/></IconBase>; }
export function DownloadIcon(props: IconProps) { return <IconBase {...props}><path d="M12 4v12m0 0 5-5m-5 5-5-5M5 20h14" {...stroke}/></IconBase>; }
export function SparkleIcon(props: IconProps) { return <IconBase {...props}><path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2L12 3Zm6 10 .8 2.2L21 16l-2.2.8L18 19l-.8-2.2L15 16l2.2-.8L18 13ZM5 13l.8 2.2L8 16l-2.2.8L5 19l-.8-2.2L2 16l2.2-.8L5 13Z" {...stroke}/></IconBase>; }
export function ShieldIcon(props: IconProps) { return <IconBase {...props}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" {...stroke}/><path d="m9 12 2 2 4-4" {...stroke}/></IconBase>; }
export function ScanIcon(props: IconProps) { return <IconBase {...props}><path d="M3 8V5a2 2 0 0 1 2-2h3m8 0h3a2 2 0 0 1 2 2v3m0 8v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3M7 12h10" {...stroke}/></IconBase>; }
export function KeyIcon(props: IconProps) { return <IconBase {...props}><circle cx="8" cy="15" r="4" {...stroke}/><path d="m11 12 8-8m-3 3 2 2m-5 1 2 2" {...stroke}/></IconBase>; }
export function EyeIcon(props: IconProps) { return <IconBase {...props}><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" {...stroke}/><circle cx="12" cy="12" r="2.5" {...stroke}/></IconBase>; }
export function MailIcon(props: IconProps) { return <IconBase {...props}><rect x="3" y="5" width="18" height="14" rx="2" {...stroke}/><path d="m3 7 9 6 9-6" {...stroke}/></IconBase>; }
export function LockIcon(props: IconProps) { return <IconBase {...props}><rect x="4" y="10" width="16" height="11" rx="2" {...stroke}/><path d="M8 10V7a4 4 0 1 1 8 0v3" {...stroke}/></IconBase>; }
export function ChevronDownIcon(props: IconProps) { return <IconBase {...props}><path d="m6 9 6 6 6-6" {...stroke}/></IconBase>; }
export function ChevronRightIcon(props: IconProps) { return <IconBase {...props}><path d="m9 18 6-6-6-6" {...stroke}/></IconBase>; }
export function MoreIcon(props: IconProps) { return <IconBase {...props}><circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="19" cy="12" r="1" fill="currentColor"/></IconBase>; }
export function FilterIcon(props: IconProps) { return <IconBase {...props}><path d="M4 6h16M7 12h10m-7 6h4" {...stroke}/></IconBase>; }
