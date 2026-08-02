import { defineStore } from 'pinia'
import { keywordsApi, type KeywordOut } from '@/api/keywords'

export const useKeywordsStore = defineStore('keywords', {
  state: () => ({
    list: [] as KeywordOut[],
    loading: false,
  }),
  actions: {
    async fetch() {
      this.loading = true
      try {
        this.list = await keywordsApi.list()
      } finally {
        this.loading = false
      }
    },
  },
})
