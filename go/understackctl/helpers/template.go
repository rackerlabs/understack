package helpers

import (
	"bytes"
	"text/template"

	"github.com/Masterminds/sprig/v3"
)

// TemplateHelper renders a template string using the provided variables
func TemplateHelper(tmplStr string, vars map[string]any) (string, error) {
	tmpl, err := template.New("tmpl").
		Funcs(sprig.TxtFuncMap()).
		Option("missingkey=error").
		Parse(tmplStr)
	if err != nil {
		return "", err
	}
	var buf bytes.Buffer
	err = tmpl.Execute(&buf, vars)
	return buf.String(), err
}
