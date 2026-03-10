export type AuthMode = "login" | "signup";

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user_id: number;
};

export type UserSession = {
  email: string;
  accessToken: string;
  tokenType: string;
  userId: number;
};
