import * as React from "react"

const MOBILE_BREAKPOINT = 768

export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(undefined)

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const onChange = () => {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    }
    
    // Set initial safely without triggering sync render warning
    const t = setTimeout(() => setIsMobile(mql.matches), 0)

    mql.addEventListener("change", onChange)
    return () => {
      mql.removeEventListener("change", onChange)
      clearTimeout(t)
    }
  }, [])

  return !!isMobile
}
