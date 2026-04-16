export interface IUser {
  id: number;
  name: string;
  email: string;
}

export type UserId = number;

export type UserName = string;

export enum UserRole {
  Admin,
  Editor,
  Viewer,
}
