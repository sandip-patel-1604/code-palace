package main

import "fmt"

const MaxConnections = 100
const internalLimit = 10

var DefaultTimeout = 30
var _privateVar = "hidden"

type User struct {
	Name  string
	Email string
}

type Greeter interface {
	Greet() string
}

func (u *User) Greet() string {
	return fmt.Sprintf("Hello, %s", u.Name)
}

func (u *User) validate() bool {
	return u.Name != ""
}

func NewUser(name, email string) *User {
	return &User{Name: name, Email: email}
}
