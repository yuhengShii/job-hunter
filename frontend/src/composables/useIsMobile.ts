import { getCurrentInstance, onBeforeUnmount, ref } from 'vue'

const MOBILE_QUERY = '(max-width: 768px)'

export function useIsMobile() {
  const isMobile = ref(false)
  const mq = window.matchMedia(MOBILE_QUERY)
  isMobile.value = mq.matches
  const onChange = (e: MediaQueryListEvent) => {
    isMobile.value = e.matches
  }
  mq.addEventListener('change', onChange)
  if (getCurrentInstance()) {
    onBeforeUnmount(() => mq.removeEventListener('change', onChange))
  }
  return isMobile
}
