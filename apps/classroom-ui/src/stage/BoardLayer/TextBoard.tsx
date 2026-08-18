import type { TextProps } from '@contracts'
import { ChalkMarkdown } from './chalkMarkdown'

const SIZE_CLASS: Record<NonNullable<TextProps['size']>, string> = {
  sm: 'text-[clamp(1.1rem,2vw,1.8rem)]',
  md: 'text-[clamp(1.3rem,2.4vw,2.2rem)]',
  lg: 'text-[clamp(1.6rem,3vw,2.8rem)]',
  xl: 'text-[clamp(2rem,3.6vw,3.4rem)]',
}

/** Chalk on the photographed board. Renders Core's chalkboard markdown grammar. */
export function TextBoard({ props }: { props: TextProps }) {
  const size = SIZE_CLASS[props.size ?? 'lg']
  return (
    <div className="flex h-full w-full items-center justify-center px-[6%] py-[8%]">
      <ChalkMarkdown key={props.text} text={props.text} textSizeClass={size} />
    </div>
  )
}
