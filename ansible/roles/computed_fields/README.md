# computed fields dynamically create a new field pulling from existing data sources already in Nautobot,

In your variables you'll need to define something like:

```yaml
computed_fields_data:
  - key: urn
    display: "Device URN"
    content_type: dcim.device
    label: "Device URN"
    description: "A string representing the URN for a device"
    template: "{%- if obj.serial and obj.role and obj.location and obj.device_type and obj.device_type.manufacturer %}\n  {%- set role = obj.role.name | lower | replace(\" \", \"-\") -%}\n  {%- set loc = obj.location.name | lower -%}\n  {%- set manufacturer = obj.device_type.manufacturer.name | lower -%}\n  {%- set serial = obj.serial | lower -%}\n  {%- set partition = \"UC_PARTITION\" | settings_or_config -%}\nurn:rax:undercloud:{{ partition }}:nautobot:{{ role }}:{{ loc }}:{{ manufacturer }}-{{ serial }} {%- endif %}"
    weight: 100
    advanced_ui: false
```

Where the `key` is the unique slug.
