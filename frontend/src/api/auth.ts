import { http } from './http'

export interface TokenResponse {
  access_token: string
  token_type: string
}

export function login(username: string, password: string): Promise<TokenResponse> {
  return http.post<TokenResponse>('/auth/login', { username, password }).then((r) => r.data)
}
