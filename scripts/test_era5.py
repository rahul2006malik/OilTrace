import cdsapi


def main():
    client = cdsapi.Client()

    client.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": ["reanalysis"],
            "variable": [
                "10m_u_component_of_wind",
                "10m_v_component_of_wind",
                "sea_surface_temperature",
                "mean_sea_level_pressure",
            ],
            "year": ["2025"],
            "month": ["01"],
            "day": ["01"],
            "time": ["12:00"],
            "data_format": "netcdf",
            "download_format": "unarchived",
            "area": [25, 65, 5, 90],
        },
        "data/test_era5.nc",
    )

    print("ERA5 test download completed.")


if __name__ == "__main__":
    main()