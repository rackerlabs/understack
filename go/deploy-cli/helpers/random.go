package helpers

import (
	"crypto/rand"
	"log"
	"math/big"
	"os"
)

func GenerateRandomString(length int) string {
	// Define the dictionary: _A-Za-z0-9
	const dictionary = "_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
	dictLen := big.NewInt(int64(len(dictionary)))

	// Buffer to hold the result
	result := make([]byte, length)

	// Generate random indices into the dictionary
	for i := 0; i < length; i++ {
		// Generate a secure random number between 0 and dictLen-1
		n, err := rand.Int(rand.Reader, dictLen)
		if err != nil {
			log.Fatal("failed to generate random password", "err", err)
			os.Exit(1)
		}
		result[i] = dictionary[n.Int64()]
	}

	return string(result)
}
