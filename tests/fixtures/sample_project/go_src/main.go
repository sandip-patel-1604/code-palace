package main

import (
	"fmt"
	"os"
	"net/http"
)

func main() {
	fmt.Println("Code Palace sample")
	os.Exit(run())
}

func run() int {
	http.HandleFunc("/", handleRoot)
	return 0
}

func handleRoot(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintln(w, "hello")
}
