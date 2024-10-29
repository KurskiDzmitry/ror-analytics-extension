import json
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s 🤖 %(message)s', datefmt='%H:%M:%S')

def to_camel_case(snake_str):
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def to_pascal_case(snake_str):
    components = snake_str.split('_')
    return ''.join(x.title() for x in components)

def to_lower_camel_case(pascal_str):
    return pascal_str[0].lower() + pascal_str[1:]

def parse_properties(properties, required):
    swift_properties = []
    initializer_params = []
    initializer_body = []
    coding_keys = []
    for prop, details in properties.items():
        swift_type = get_swift_type(details, prop)
        is_optional = prop not in required
        default_value = details.get("default")
        description = details.get("description", "")
        description_comment = f"    /// {description}" if description else ""
        camel_case_prop = to_camel_case(prop)
        json_key = details.get("key", prop)
        
        if default_value is not None:
            default_value_str = get_default_value_str(default_value, swift_type)
            swift_properties.append(f"{description_comment}\n    let {camel_case_prop}: {swift_type} = {default_value_str}")
        else:
            swift_properties.append(f"{description_comment}\n    let {camel_case_prop}: {swift_type}{'?' if is_optional else ''}")
            initializer_params.append(f"{camel_case_prop}: {swift_type}{'?' if is_optional else ''}")
            initializer_body.append(f"        self.{camel_case_prop} = {camel_case_prop}")
        
        coding_keys.append(f"        case {camel_case_prop} = \"{json_key}\"")
    
    return swift_properties, initializer_params, initializer_body, coding_keys

def get_swift_type(details, prop_name):
    if details["type"] == "array" and "items" in details:
        item_type = get_swift_type(details["items"], prop_name[:-1])
        return f"[{item_type}]"
    elif details["type"] == "object":
        return details.get("title", to_pascal_case(prop_name))
    
    type_mapping = {
        "string": "String",
        "integer": "Int",
        "number": "Double",
        "array": f"[{to_pascal_case(prop_name[:-1])}]",
        "object": to_pascal_case(prop_name)
    }
    return type_mapping.get(details["type"], "Any")

def get_default_value_str(default_value, swift_type):
    if swift_type == "String":
        return f'"{default_value}"'
    elif swift_type == "Int" or swift_type == "Double":
        return str(default_value)
    elif swift_type.startswith("["):
        return str(default_value).replace("'", '"')
    else:
        return str(default_value)

def generate_struct(name, schema, nested_structs, is_main_struct=False):
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    swift_properties, initializer_params, initializer_body, coding_keys = parse_properties(properties, required)
    
    struct_name = schema.get("title", to_pascal_case(name))
    visibility = "public " if is_main_struct else ""
    
    struct = []
    if is_main_struct:
        struct.append("import Foundation")
        struct.append("")
    
    struct.extend([
        f"{visibility}struct {struct_name}: Codable {{",
        *swift_properties,
        "",
        "    enum CodingKeys: String, CodingKey {",
        *coding_keys,
        "    }",
        "",
        f"    init({', '.join(initializer_params)}) {{",
        *initializer_body,
        "    }",
    ])
    
    for nested_struct, _ in nested_structs:
        struct.append("")
        struct.append(indent(nested_struct, 1))
    
    struct.append("}")
    
    return "\n".join(struct), struct_name

def generate_nested_structs(properties):
    nested_structs = []
    for prop, details in properties.items():
        if details["type"] == "array" and "items" in details:
            nested_struct, _ = generate_struct(details["items"].get("title", f"{prop[:-1]}"), details["items"], [])
            nested_structs.append((nested_struct, details["items"].get("title", f"{prop[:-1]}")))
        elif details["type"] == "object":
            nested_struct, _ = generate_struct(details.get("title", prop), details, [])
            nested_structs.append((nested_struct, details.get("title", prop)))
    return nested_structs

def indent(text, level):
    indentation = "    " * level
    return "\n".join(indentation + line if line else line for line in text.split("\n"))

def write_to_file(directory, filename, content):
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(os.path.join(directory, filename), "w") as file:
        file.write(content)

def append_to_file(directory, filename, content):
    with open(os.path.join(directory, filename), "a") as file:
        file.write(content)

def generate_extension_code(struct_name, product_items_properties, required_properties):
    array_properties = []
    for prop, details in product_items_properties.items():
        swift_type = get_swift_type(details, prop)
        camel_case_prop = to_camel_case(prop)
        is_optional = prop not in required_properties
        json_key = details.get("key", prop)
        array_properties.append((json_key, camel_case_prop, swift_type, is_optional))
    
    array_initializations = "\n        ".join([f"var {camel_case_prop}s: [{swift_type}] = []" for _, camel_case_prop, swift_type, _ in array_properties])
    
    array_appends = []
    for json_key, camel_case_prop, swift_type, is_optional in array_properties:
        if is_optional and swift_type == "String":
            array_appends.append(f"{camel_case_prop}s.append(item.{camel_case_prop} ?? \"\")")
        else:
            array_appends.append(f"{camel_case_prop}s.append(item.{camel_case_prop})")
    
    array_appends_str = "\n            ".join(array_appends)
    dictionary_assignments = "\n            ".join([f'dictionary["{json_key}"] = {camel_case_prop}s' for json_key, camel_case_prop, _, _ in array_properties])
    
    extension_code = rf"""
extension {struct_name} {{
    
    func convertToDictionary() -> [String: Any] {{
        {array_initializations}
        
        for item in self.productItems {{
            {array_appends_str}
        }}
        
        let encoder = JSONEncoder()
        do {{
            let data = try encoder.encode(self)
            var dictionary = try JSONSerialization.jsonObject(with: data, options: .allowFragments) as? [String: Any] ?? [:]
            
            // Add the individual product item arrays to the dictionary
            {dictionary_assignments}
            
            // Remove the original productItems key
            dictionary.removeValue(forKey: "productItems")
            
            return PayloadValidator.checkPayload(dictionary)
        }} catch {{
            print("Error converting to dictionary: \\(error)")
            return [:] // Return an empty dictionary in case of error
        }}
    }}
}}
"""
    return extension_code

def generate_ror_analytics_extension(schema, struct_name):
    api_name = schema.get("x-api-name", "trackEvent")
    api_event_type = schema.get("x-api-event-type", "event")
    api_description = schema.get("x-api-description", "Track an event to the RAT platform")
    
    # Convert struct name to lower camel case for the parameter name
    camel_case_struct_name = to_lower_camel_case(struct_name)
    
    extension_code = f"""
    /// {api_description}
    static func {api_name}(_ {camel_case_struct_name}: {struct_name}) {{
        RAnalyticsRATTracker.shared().event(
            withEventType: "{api_event_type}",
            parameters: {camel_case_struct_name}.convertToDictionary()).track()
    }}
"""
    return extension_code

def list_json_files(directory):
    return [f for f in os.listdir(directory) if f.endswith('.json')]

def generate_payload_validator(directory):
    payload_validator_content = """import Foundation

struct PayloadValidator {
    
    static func checkPayload(_ payload: [String: Any]) -> [String: Any] {
        var updatedPayload = payload
        
        for (key, value) in updatedPayload {
            updatedPayload[key] = checkValue(value, key: key)
        }
        
        return updatedPayload
    }
    
    private static func checkValue(_ value: Any, key: String?) -> Any {
        switch value {
        case let str as String:
            if str.isEmpty {
                print("⚠️ RoRAnalyticsWrapper: \\(key ?? "unknown key") is empty")
            }
            return value
            
        case let usignedInt as UInt:
            if key == "chkout", usignedInt != 50 {
                print("⚠️ RoRAnalyticsWrapper: Checkout confirmation page value \\(value) must be 50.")
            }
            return value
            
        case let array as [Any]:
            return checkArray(array, key: key)
            
        case let nestedDict as [String: Any]:
            return checkPayload(nestedDict)
            
        default:
            return value
        }
    }
    
    private static func checkArray(_ array: [Any], key: String?) -> [Any] {
        var updatedArray = array
        
        for (index, element) in updatedArray.enumerated() {
            updatedArray[index] = checkValue(element, key: key.map { "\\(0) at index \\(index)" })
        }
        
        return updatedArray
    }
    
}
"""
    write_to_file(directory, "PayloadValidator.swift", payload_validator_content)

def main():
    schemas_dir = "Schema"
    source_dir = "Sources"
    object_model_dir = os.path.join(source_dir, "ObjectModel")
    extension_dir = os.path.join(source_dir, "Extension")
    
    logging.info("Ensuring source directories exist")
    # Ensure the source directories exist
    if not os.path.exists(object_model_dir):
        os.makedirs(object_model_dir)
    if not os.path.exists(extension_dir):
        os.makedirs(extension_dir)
    
    logging.info("Listing JSON files in the schemas directory")
    json_files = list_json_files(schemas_dir)
    
    # Initialize the RoRAnalyticsExtension file with imports
    ror_analytics_extension_file = os.path.join(extension_dir, "RoRAnalyticsExtension.swift")
    if not os.path.exists(ror_analytics_extension_file):
        with open(ror_analytics_extension_file, "w") as file:
            file.write("import Foundation\nimport RakutenAnalytics\n\npublic extension RAnalyticsRATTracker {\n")
    
    # Read the existing content of the RoRAnalyticsExtension file
    with open(ror_analytics_extension_file, "r") as file:
        existing_content = file.read()
    
    for json_file in json_files:
        logging.info(f"Processing JSON file: {json_file}")
        with open(os.path.join(schemas_dir, json_file), "r") as file:
            schema = json.load(file)
        
        # Generate nested structs
        logging.info("Generating nested structs")
        nested_structs = generate_nested_structs(schema.get("properties", {}))
        
        # Generate main struct with nested structs
        logging.info("Generating main struct")
        main_struct, struct_name = generate_struct(schema.get("title", "checkout_complete_pageview_event"), schema, nested_structs, is_main_struct=True)
        
        # Use the struct name for the output file
        output_file = f"{struct_name}.swift"
        
        # Extract productItems properties from the schema
        product_items_properties = schema["properties"]["productItems"]["items"]["properties"]
        required_properties = schema["properties"]["productItems"]["items"].get("required", [])
        
        # Generate extension code
        logging.info("Generating extension code")
        extension_code = generate_extension_code(struct_name, product_items_properties, required_properties)
        
        # Combine main struct and extension code
        full_content = f"{main_struct}\n{extension_code}"
        
        # Write to file in ObjectModel directory
        logging.info(f"Writing to file: {output_file}")
        write_to_file(object_model_dir, output_file, full_content)
        
        # Generate RoRAnalyticsExtension code
        logging.info("Generating RoRAnalyticsExtension code")
        ror_analytics_extension_code = generate_ror_analytics_extension(schema, struct_name)
        
        # Check if the method already exists in the existing content
        if ror_analytics_extension_code.strip() not in existing_content:
            # Append RoRAnalyticsExtension to file
            logging.info("Appending RoRAnalyticsExtension code to file")
            append_to_file(extension_dir, "RoRAnalyticsExtension.swift", ror_analytics_extension_code)
    
    # Ensure the extension block is closed only once
    if not existing_content.strip().endswith("}"):
        with open(ror_analytics_extension_file, "a") as file:
            file.write("}\n")
    
    # Generate PayloadValidator.swift file in Extension directory
    logging.info("Generating PayloadValidator.swift file")
    generate_payload_validator(extension_dir)

if __name__ == "__main__":
    main()
