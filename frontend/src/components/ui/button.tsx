/**
 * Button — shadcn 種子（§6.4：僅作可修改元件種子，非視覺模板）。
 * 視覺值全部來自 tokens.css（經 globals.css @theme 映射），無 shadcn 預設識別。
 */
import { forwardRef } from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const buttonVariants = cva(
  // 基線：Precise（小圓角 token）/ motion token / focus ring 走 globals :focus-visible
  "inline-flex items-center justify-center gap-2 rounded-md font-medium " +
    "transition-colors duration-[var(--ems-motion-duration-fast)] ease-standard " +
    "disabled:pointer-events-none disabled:opacity-50 select-none",
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-fg-inverse hover:bg-accent-strong shadow-glow-accent",
        secondary:
          "bg-surface-raised text-fg border border-line hover:border-line-strong",
        ghost: "text-fg-secondary hover:text-fg hover:bg-surface-raised",
        danger: "bg-danger text-fg-inverse hover:opacity-90",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-9 px-4 text-sm",
        lg: "h-10 px-5 text-base",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        type={asChild ? type : (type ?? "button")}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
